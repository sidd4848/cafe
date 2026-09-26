"""
Wait-time and readiness engine.

Model (queue-v1)
----------------
* Each menu item has a prep time learned online: an EWMA of observed
  (readyAt - startedAt), split across the order's units in proportion to their estimates.
* An order's prep time is  max(unit) + 0.35 x (sum of the other units): a barista batches
  within one order, so a second latte costs far less than the first.
* The queue is simulated as `baristasOnShift` parallel workers. Orders in progress hold a
  worker until their remaining time runs out; placed orders are taken FIFO by the next
  free worker. That yields each order's ready time, and the queue position falls out too.
* The confidence band comes from the summed prep-time variance plus the model's recent
  absolute error, so it widens honestly when predictions have been off.

`recompute()` runs on every state change in a cafe (order placed, started, ready,
collected or cancelled, staff changing the barista count, and a one-minute sweep). It
rewrites `eta` on every active order and `stats/live`; clients hold realtime listeners on
those docs, which is what makes the waiting time dynamic.

Pre-orders (`status: scheduled`) sit outside the queue until the queue is short enough
that, if released now, they'd be ready at their pickup time. The same check serves both
"pick up at 5:30pm" and "ready when I arrive in 12 minutes".
"""

import heapq
import logging
import math
import statistics
from datetime import datetime, timedelta

from google.cloud import firestore

from app.db import db, now
from app.services import menu as menu_svc

logger = logging.getLogger(__name__)

MODEL_VERSION = "queue-v1"
BATCH_FACTOR = 0.35
ALPHA = 0.2
Z80 = 1.28  # 80% band
RELEASE_SLACK_SEC = 60
TYPICAL_ORDER_SEC = 140


def item_prep(menu: dict, item_id: str) -> tuple[float, float]:
    item = menu.get(item_id) or {}
    mean = float(item.get("prepSecEwma") or item.get("prepSecBase") or TYPICAL_ORDER_SEC)
    var = float(item.get("prepSecVar") or (0.25 * mean) ** 2)
    return mean, var


def order_prep(order: dict, menu: dict) -> tuple[float, float]:
    units: list[tuple[float, float]] = []
    for line in order.get("items", []):
        units += [item_prep(menu, line["itemId"])] * int(line.get("qty", 1))
    if not units:
        return 0.0, 0.0
    means = sorted((m for m, _ in units), reverse=True)
    prep = means[0] + BATCH_FACTOR * sum(means[1:])
    var = max(v for _, v in units) + BATCH_FACTOR ** 2 * sum(v for _, v in units[1:])
    return prep, var


def _ts(value) -> datetime | None:
    return value if isinstance(value, datetime) else None


def recompute(cafe_id: str) -> dict:
    """Rebuild the queue, release due pre-orders, and write every ETA. Returns live stats."""
    cafe = menu_svc.get_cafe(cafe_id)
    menu = menu_svc.get_menu(cafe_id)
    t = now()
    workers = max(1, int(cafe.get("baristasOnShift", 1)))
    overhead = float(cafe.get("etaOverheadSec", 45))

    stats_ref = db().collection("cafes").document(cafe_id).collection("stats").document("live")
    stats_snap = stats_ref.get()
    stats = stats_snap.to_dict() if stats_snap.exists else {}
    err_ewma = float(stats.get("etaAbsErrorEwmaSec", 60))

    snaps = (
        db().collection("orders")
        .where(filter=firestore.FieldFilter("cafeId", "==", cafe_id))
        .where(filter=firestore.FieldFilter("status", "in", ["scheduled", "placed", "in_progress"]))
        .stream()
    )
    orders = [{"id": s.id, "_ref": s.reference, **s.to_dict()} for s in snaps]
    in_progress = sorted((o for o in orders if o["status"] == "in_progress"),
                         key=lambda o: _ts(o.get("startedAt")) or t)
    placed = sorted((o for o in orders if o["status"] == "placed"),
                    key=lambda o: _ts(o.get("placedAt")) or t)
    scheduled = sorted((o for o in orders if o["status"] == "scheduled"),
                       key=lambda o: _ts(o.get("scheduledFor")) or t)

    free = [t.timestamp()] * workers  # when each barista is next free, epoch seconds
    heapq.heapify(free)
    updates: dict[str, dict] = {}
    queue_var = 0.0
    position = 0

    def schedule(o: dict, started: bool) -> None:
        nonlocal queue_var, position
        prep, var = order_prep(o, menu)
        slot = heapq.heappop(free)
        if started:
            elapsed = t.timestamp() - (_ts(o.get("startedAt")) or t).timestamp()
            done = t.timestamp() + max(15.0, prep - elapsed)
        else:
            done = max(slot, t.timestamp()) + prep
        heapq.heappush(free, done)
        position += 1
        band = max(30.0, Z80 * math.sqrt(var + queue_var / workers) + 0.5 * err_ewma)
        queue_var += var
        ready = datetime.fromtimestamp(done + overhead, tz=t.tzinfo)
        eta = {
            "readyAt": ready,
            "lowAt": ready - timedelta(seconds=band * 0.6),
            "highAt": ready + timedelta(seconds=band),
            "queuePosition": position,
            "updatedAt": t,
            "modelVersion": MODEL_VERSION,
        }
        upd = {"eta": eta}
        if not o.get("etaAtPlacement"):
            upd["etaAtPlacement"] = ready
        updates[o["id"]] = upd

    for o in in_progress:
        schedule(o, started=True)
    for o in placed:
        schedule(o, started=False)

    # Release pre-orders whose pickup time is now within reach of the queue.
    for o in scheduled:
        target = _ts(o.get("scheduledFor")) or t
        prep, _ = order_prep(o, menu)
        earliest_ready = max(free[0], t.timestamp()) + prep + overhead
        if earliest_ready >= target.timestamp() - RELEASE_SLACK_SEC:
            o["status"], o["placedAt"] = "placed", t
            schedule(o, started=False)
            updates[o["id"]].update({"status": "placed", "placedAt": t, "releasedAt": t})
        else:
            updates[o["id"]] = {"eta": {
                "readyAt": target, "lowAt": target, "highAt": target + timedelta(minutes=2),
                "queuePosition": None, "updatedAt": t, "modelVersion": MODEL_VERSION,
                "releaseAt": target - timedelta(seconds=prep + overhead + RELEASE_SLACK_SEC),
            }}

    batch = db().batch()
    refs = {o["id"]: o["_ref"] for o in orders}
    for oid, upd in updates.items():
        batch.update(refs[oid], upd)

    active = in_progress + placed + [o for o in scheduled if o["status"] == "placed"]
    queued_items = sum(int(l.get("qty", 1)) for o in active for l in o.get("items", []))
    current_wait = max(free[0], t.timestamp()) - t.timestamp() + TYPICAL_ORDER_SEC + overhead
    live = {
        "activeOrders": len(active),
        "queuedItems": queued_items,
        "scheduledOrders": sum(1 for o in scheduled if o["status"] == "scheduled"),
        "currentWaitSec": round(current_wait),
        "baristasOnShift": workers,
        "etaAbsErrorEwmaSec": round(err_ewma),
        "updatedAt": t,
    }
    batch.set(stats_ref, live, merge=True)
    batch.commit()
    return live


def earliest_ready(cafe_id: str, order_like: dict) -> datetime:
    """When an order with these items would be ready if it joined the queue right now."""
    cafe = menu_svc.get_cafe(cafe_id)
    menu = menu_svc.get_menu(cafe_id)
    snap = db().collection("cafes").document(cafe_id).collection("stats").document("live").get()
    wait_ahead = max(0.0, float((snap.to_dict() or {}).get("currentWaitSec", 0)) - TYPICAL_ORDER_SEC
                     - float(cafe.get("etaOverheadSec", 45))) if snap.exists else 0.0
    prep, _ = order_prep(order_like, menu)
    return now() + timedelta(seconds=wait_ahead + prep + float(cafe.get("etaOverheadSec", 45)))


def learn_from_completion(cafe_id: str, order: dict, ready_at: datetime) -> None:
    """Fold one finished order into item prep times and the model's error tracker."""
    menu = menu_svc.get_menu(cafe_id)
    started = _ts(order.get("startedAt"))
    if started:
        observed = (ready_at - started).total_seconds()
        est, _ = order_prep(order, menu)
        # Ignore obviously broken observations (board left open, accidental taps).
        if 10 <= observed <= 1800 and est > 0:
            ratio = observed / est
            menu_ref = db().collection("cafes").document(cafe_id).collection("menu")
            for item_id in {l["itemId"] for l in order.get("items", [])}:
                mean, var = item_prep(menu, item_id)
                sample = mean * ratio
                new_mean = (1 - ALPHA) * mean + ALPHA * sample
                new_var = (1 - ALPHA) * var + ALPHA * (sample - new_mean) ** 2
                menu_ref.document(item_id).update({"prepSecEwma": new_mean, "prepSecVar": new_var})
            menu_svc.invalidate(cafe_id)

    predicted = _ts(order.get("etaAtPlacement"))
    if predicted:
        err = abs((ready_at - predicted).total_seconds())
        stats_ref = db().collection("cafes").document(cafe_id).collection("stats").document("live")
        snap = stats_ref.get()
        prev = float((snap.to_dict() or {}).get("etaAbsErrorEwmaSec", 60)) if snap.exists else 60.0
        errors = list((snap.to_dict() or {}).get("recentErrorsSec", []))[-49:] + [round(err)]
        stats_ref.set({
            "etaAbsErrorEwmaSec": round((1 - ALPHA) * prev + ALPHA * err),
            "recentErrorsSec": errors,
            "etaErrorP50Sec": round(statistics.median(errors)),
        }, merge=True)
