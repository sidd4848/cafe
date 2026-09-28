"""
Peak-shaving engine: move the rush into the quiet hours.

1. Forecast   Expected wait per 30-min slot (busyness profile + today's live deviation).
              Peak = expected wait >= PEAK_WAIT_SEC; quiet = <= QUIET_WAIT_SEC.
2. Target     A guest whose habitual (or current) order time falls in a peak gets an offer
              to pick up in the nearest quiet slot. Offered only when their shift
              propensity is high enough: flexible visit times, past acceptances, tier.
3. Incentive  Bonus beans chosen per café by Thompson sampling over arms {10, 20, 30},
              maximising P(accept) x (value of a shifted peak order - beans paid).
4. Redeem     The offer becomes a timed pre-order; beans are awarded when the order is
              placed for the offered slot. Outcomes feed back into the arm statistics.

Impact is measured before/after `peakEngineSince`: share of orders in peak hours, wait
in peak hours, estimated walk-outs (a wait-sensitivity curve) and revenue recovered.
"""

import logging
import math
import random
import statistics
from datetime import datetime, timedelta

from fastapi import HTTPException
from google.cloud import firestore

from app.db import db, now
from app.services import busyness, loyalty
from app.services import menu as menu_svc

logger = logging.getLogger(__name__)

PEAK_WAIT_SEC = 300
QUIET_WAIT_SEC = 240
ARMS = [10, 20, 30]
SHIFT_VALUE_BEANS = 45      # what moving one order out of the peak is worth, in beans
MIN_PROPENSITY = 0.35
REDEEM_TOLERANCE = timedelta(minutes=15)
OFFER_TTL = timedelta(hours=3)


def _slot_label(dt: datetime) -> str:
    return dt.strftime("%H:%M")


# ---- 1. Forecast -------------------------------------------------------------------

def forecast(cafe_id: str, date_local: str | None = None) -> dict:
    bt = busyness.best_times(cafe_id, date_local)
    slots = []
    for s in bt["slots"]:
        w = s["expectedWaitSec"]
        kind = "peak" if w >= PEAK_WAIT_SEC else "quiet" if w <= QUIET_WAIT_SEC else "normal"
        slots.append({**s, "kind": kind})
    windows = []
    for s in slots:
        if s["kind"] != "peak":
            continue
        start = datetime.fromisoformat(s["start"])
        if windows and windows[-1]["end"] == start:
            windows[-1]["end"] = start + timedelta(minutes=30)
            windows[-1]["maxWaitSec"] = max(windows[-1]["maxWaitSec"], s["expectedWaitSec"])
        else:
            windows.append({"start": start, "end": start + timedelta(minutes=30), "maxWaitSec": s["expectedWaitSec"]})
    return {"date": bt["date"], "slots": slots,
            "peaks": [{"start": w["start"].isoformat(), "end": w["end"].isoformat(), "maxWaitSec": w["maxWaitSec"]}
                      for w in windows],
            "thresholds": {"peakWaitSec": PEAK_WAIT_SEC, "quietWaitSec": QUIET_WAIT_SEC}}


def _slot_at(fc: dict, at: datetime) -> dict | None:
    for s in fc["slots"]:
        start = datetime.fromisoformat(s["start"])
        if start <= at < start + timedelta(minutes=30):
            return s
    return None


def _quiet_alternative(fc: dict, at: datetime) -> datetime | None:
    """Nearest quiet slot within -60/+120 min of `at`, preferring later (fresher to wait)."""
    best, best_cost = None, None
    for s in fc["slots"]:
        if s["kind"] != "quiet":
            continue
        start = datetime.fromisoformat(s["start"]) + timedelta(minutes=10)
        delta = (start - at).total_seconds() / 60
        if delta < -60 or delta > 120 or start < now() + timedelta(minutes=10):
            continue
        cost = delta if delta >= 0 else -delta * 1.5
        if best_cost is None or cost < best_cost:
            best, best_cost = start, cost
    return best


# ---- 2. Targeting ------------------------------------------------------------------

def habit(uid: str, cafe_id: str) -> dict | None:
    """Typical local order time (minutes after midnight) and its spread, last 60 days."""
    cafe = menu_svc.get_cafe(cafe_id)
    zone = menu_svc.tz(cafe)
    since = now() - timedelta(days=60)
    mins = []
    for s in (db().collection("orders").where(filter=firestore.FieldFilter("uid", "==", uid))
              .order_by("createdAt", direction=firestore.Query.DESCENDING).limit(60).stream()):
        o = s.to_dict()
        placed = o.get("scheduledFor") or o.get("createdAt")
        if o.get("cafeId") != cafe_id or o.get("status") == "cancelled" or not placed or placed < since:
            continue
        local = placed.astimezone(zone)
        mins.append(local.hour * 60 + local.minute)
    if not mins:
        return None
    return {"minute": statistics.median(mins), "spread": statistics.pstdev(mins) if len(mins) > 1 else 45.0,
            "orders": len(mins)}


def _user_accept_rate(uid: str) -> tuple[int, int]:
    offered = accepted = 0
    for s in db().collection("nudges").where(filter=firestore.FieldFilter("uid", "==", uid)).limit(50).stream():
        n = s.to_dict()
        if n["status"] in {"accepted", "declined", "redeemed", "expired"}:
            offered += 1
            accepted += n["status"] in {"accepted", "redeemed"}
    return offered, accepted


def propensity(uid: str, user: dict, h: dict | None) -> float:
    offered, accepted = _user_accept_rate(uid)
    rate = (accepted + 1) / (offered + 2)
    flex = min(1.0, (h["spread"] if h else 45.0) / 90)
    tier = {"Bean": 0.4, "Roast": 0.7, "Reserve": 1.0}[loyalty.summary(user)["tier"]]
    return round(0.2 + 0.3 * flex + 0.3 * rate + 0.2 * tier, 3)


# ---- 3. Incentive bandit -----------------------------------------------------------

def _arm_stats(cafe_id: str) -> dict:
    snap = db().collection("cafes").document(cafe_id).collection("stats").document("nudges").get()
    arms = (snap.to_dict() or {}).get("arms", {}) if snap.exists else {}
    return {str(a): arms.get(str(a), {"offered": 0, "accepted": 0}) for a in ARMS}


def choose_beans(cafe_id: str) -> int:
    arms = _arm_stats(cafe_id)
    best, best_val = ARMS[0], -1.0
    for a in ARMS:
        st = arms[str(a)]
        p = random.betavariate(st["accepted"] + 1, st["offered"] - st["accepted"] + 1)
        val = p * (SHIFT_VALUE_BEANS - a)
        if val > best_val:
            best, best_val = a, val
    return best


def _record_arm(cafe_id: str, beans: int, field: str) -> None:
    ref = db().collection("cafes").document(cafe_id).collection("stats").document("nudges")
    ref.set({"arms": {str(beans): {field: firestore.Increment(1)}}}, merge=True)


# ---- Offers ------------------------------------------------------------------------

def _existing(uid: str, cafe_id: str, day: str) -> dict | None:
    for s in (db().collection("nudges").where(filter=firestore.FieldFilter("uid", "==", uid))
              .where(filter=firestore.FieldFilter("day", "==", day)).stream()):
        n = s.to_dict()
        if n["cafeId"] == cafe_id:
            return {"id": s.id, **n}
    return None


def offer(cafe_id: str, uid: str, user: dict, context: str) -> dict | None:
    """Return (creating if warranted) today's peak-shift offer for this guest."""
    cafe = menu_svc.get_cafe(cafe_id)
    zone = menu_svc.tz(cafe)
    t = now()
    day = t.astimezone(zone).date().isoformat()
    existing = _existing(uid, cafe_id, day)
    if existing:
        if existing["status"] == "offered" and existing["expiresAt"] > t and existing["toAt"] > t:
            return existing
        return None

    fc = forecast(cafe_id)
    h = habit(uid, cafe_id)
    if context == "checkout":
        at = t
    else:
        if not h:
            return None
        local = t.astimezone(zone)
        at = local.replace(hour=int(h["minute"] // 60), minute=int(h["minute"] % 60), second=0, microsecond=0)
        if at < t - timedelta(minutes=15) or at > t + timedelta(hours=4):
            return None
    slot = _slot_at(fc, at)
    if not slot or slot["kind"] != "peak":
        return None
    to_at = _quiet_alternative(fc, at)
    if not to_at:
        return None
    score = propensity(uid, user, h)
    if score < MIN_PROPENSITY and context != "checkout":
        return None

    beans = choose_beans(cafe_id)
    doc = {
        "uid": uid, "cafeId": cafe_id, "day": day, "context": context,
        "fromAt": at, "toAt": to_at, "fromWaitSec": slot["expectedWaitSec"],
        "toWaitSec": (_slot_at(fc, to_at) or {}).get("expectedWaitSec"),
        "beans": beans, "propensity": score, "status": "offered",
        "createdAt": t, "expiresAt": min(t + OFFER_TTL, to_at),
    }
    ref = db().collection("nudges").document()
    ref.set(doc)
    _record_arm(cafe_id, beans, "offered")
    db().collection("cafes").document(cafe_id).set({"peakEngineSince": cafe.get("peakEngineSince") or t}, merge=True)
    menu_svc.invalidate(cafe_id)
    return {"id": ref.id, **doc}


def respond(uid: str, nudge_id: str, accept: bool) -> dict:
    ref = db().collection("nudges").document(nudge_id)
    snap = ref.get()
    if not snap.exists or snap.get("uid") != uid:
        raise HTTPException(404, "Offer not found.")
    n = snap.to_dict()
    if n["status"] != "offered":
        raise HTTPException(409, "This offer has already been used.")
    ref.update({"status": "accepted" if accept else "declined", "respondedAt": now()})
    if accept:
        _record_arm(n["cafeId"], n["beans"], "accepted")
    return {"status": "accepted" if accept else "declined", "pickupAt": n["toAt"].isoformat()}


def redeem(uid: str, nudge_id: str | None, pickup_at: datetime | None, order_id: str) -> dict | None:
    """Called at checkout: award the beans if the order is for the offered slot."""
    if not nudge_id or not pickup_at:
        return None
    ref = db().collection("nudges").document(nudge_id)
    snap = ref.get()
    if not snap.exists or snap.get("uid") != uid:
        return None
    n = snap.to_dict()
    if n["status"] == "offered":
        _record_arm(n["cafeId"], n["beans"], "accepted")
    elif n["status"] != "accepted":
        return None
    if abs(pickup_at - n["toAt"]) > REDEEM_TOLERANCE:
        return None
    ref.update({"status": "redeemed", "orderId": order_id, "redeemedAt": now()})
    loyalty.bonus(uid, n["beans"])
    return {"id": nudge_id, "beans": n["beans"]}


# ---- 4. Impact ---------------------------------------------------------------------

def walkout_prob(wait_sec: float) -> float:
    """Share of would-be guests who leave when they see this wait (industry-style curve)."""
    return max(0.0, min(0.35, (wait_sec - 240) / 1500))


def _peak_hours(cafe_id: str) -> set[tuple[int, int]]:
    """(dow, hour) cells that the *prior* profile marks as peak: a fixed yardstick."""
    out = set()
    for dow in range(7):
        for h, cell in enumerate(busyness.prior_hourly(dow)):
            if cell["avgWaitSec"] >= PEAK_WAIT_SEC:
                out.add((dow, h))
    return out


def impact(cafe_id: str, days: int = 7) -> dict:
    cafe = menu_svc.get_cafe(cafe_id)
    zone = menu_svc.tz(cafe)
    t = now()
    since = cafe.get("peakEngineSince") or t
    start = since - timedelta(days=days)
    peaks = _peak_hours(cafe_id)
    periods = {"before": {"orders": 0, "peakOrders": 0, "peakWaits": [], "revenue": 0, "walkouts": 0.0, "days": set()},
               "after": {"orders": 0, "peakOrders": 0, "peakWaits": [], "revenue": 0, "walkouts": 0.0, "days": set()}}
    for s in (db().collection("orders").where(filter=firestore.FieldFilter("cafeId", "==", cafe_id))
              .where(filter=firestore.FieldFilter("placedAt", ">=", start)).stream()):
        o = s.to_dict()
        placed = o.get("placedAt")
        if not isinstance(placed, datetime) or o.get("status") == "cancelled":
            continue
        p = periods["before" if placed < since else "after"]
        local = placed.astimezone(zone)
        p["orders"] += 1
        p["revenue"] += o.get("total", 0)
        p["days"].add(local.date())
        if (local.weekday(), local.hour) in peaks:
            p["peakOrders"] += 1
            ready = o.get("readyAt")
            if isinstance(ready, datetime):
                w = (ready - placed).total_seconds()
                p["peakWaits"].append(w)
                q = walkout_prob(w)
                p["walkouts"] += q / (1 - q)   # guests lost for each guest served at that wait

    def summarise(p: dict) -> dict:
        n_days = max(1, len(p["days"]))
        return {
            "days": len(p["days"]),
            "ordersPerDay": round(p["orders"] / n_days, 1),
            "peakShare": round(p["peakOrders"] / p["orders"], 3) if p["orders"] else None,
            "peakWaitSec": round(statistics.median(p["peakWaits"])) if p["peakWaits"] else None,
            "walkoutsPerDay": round(p["walkouts"] / n_days, 1),
            "avgTicket": round(p["revenue"] / p["orders"]) if p["orders"] else 0,
        }

    before, after = summarise(periods["before"]), summarise(periods["after"])
    avoided = max(0.0, before["walkoutsPerDay"] - after["walkoutsPerDay"]) if before["days"] and after["days"] else 0.0
    ticket = after["avgTicket"] or before["avgTicket"]

    nudges = {"offered": 0, "accepted": 0, "redeemed": 0, "beans": 0}
    for s in (db().collection("nudges").where(filter=firestore.FieldFilter("cafeId", "==", cafe_id))
              .where(filter=firestore.FieldFilter("createdAt", ">=", since)).stream()):
        n = s.to_dict()
        nudges["offered"] += 1
        nudges["accepted"] += n["status"] in {"accepted", "redeemed"}
        if n["status"] == "redeemed":
            nudges["redeemed"] += 1
            nudges["beans"] += n["beans"]
    arms = _arm_stats(cafe_id)
    return {
        "since": since.isoformat(), "demoData": bool(cafe.get("demoData")),
        "before": before, "after": after,
        "walkoutsAvoidedPerDay": round(avoided, 1),
        "revenueRecoveredPerDay": round(avoided * ticket),
        "revenueRecoveredPerMonth": round(avoided * ticket * 30),
        "nudges": {**nudges, "acceptRate": round(nudges["accepted"] / nudges["offered"], 3) if nudges["offered"] else None},
        "arms": [{"beans": a, **arms[str(a)],
                  "rate": round(arms[str(a)]["accepted"] / arms[str(a)]["offered"], 3) if arms[str(a)]["offered"] else None}
                 for a in ARMS],
    }


# ---- Demo data (for sales demos before a café has history) -------------------------

def simulate_demo(cafe_id: str, days: int = 14, shift_rate: float = 0.22) -> dict:
    """
    Two weeks of synthetic history: the first half without the engine (peaky), the
    second half with it (a share of peak orders nudged into nearby quiet slots, with
    bandit outcomes). Everything is tagged `synthetic` and removable with clear_demo().
    """
    clear_demo(cafe_id)
    cafe = menu_svc.get_cafe(cafe_id)
    zone = menu_svc.tz(cafe)
    menu = [i for i in menu_svc.get_menu(cafe_id).values() if i.get("available", True)]
    drinks = [i for i in menu if i["category"] in {"hot_coffee", "cold_coffee", "manual_brew", "not_coffee"}]
    t = now()
    since = t - timedelta(days=days // 2)
    rng = random.Random(42)
    arm_rate = {10: 0.18, 20: 0.31, 30: 0.36}
    arms = {str(a): {"offered": 0, "accepted": 0} for a in ARMS}
    writes: list[tuple[str, dict]] = []
    peaks = _peak_hours(cafe_id)

    for d in range(days, 0, -1):
        day = (t - timedelta(days=d)).astimezone(zone)
        prior = busyness.prior_hourly(day.weekday())
        engine_on = (t - timedelta(days=d)) >= since
        demand: dict[int, list[int]] = {h: [] for h in range(24)}  # hour -> list of minute offsets
        for h in range(24):
            lam = prior[h]["orders"] * 1.35
            n = max(0, round(rng.gauss(lam, math.sqrt(lam)))) if lam else 0
            demand[h] += [rng.randint(0, 59) for _ in range(n)]
        if engine_on:
            for h in range(24):
                if (day.weekday(), h) not in peaks:
                    continue
                keep = []
                for m in demand[h]:
                    beans = rng.choice(ARMS)
                    if rng.random() < shift_rate / 0.3 * arm_rate[beans] * 0.9:
                        arms[str(beans)]["offered"] += 1
                        arms[str(beans)]["accepted"] += 1
                        target = h + rng.choice([-2, 1, 2, 2]) if 0 < h < 23 else h
                        target = max(8, min(22, target))
                        if (day.weekday(), target) in peaks:
                            target = max(8, min(22, h + 2))
                        demand[target].append(rng.randint(0, 59))
                        writes.append(("nudge", {"uid": f"demo-guest-{rng.randint(1, 80)}", "cafeId": cafe_id,
                                                  "day": day.date().isoformat(), "context": "home",
                                                  "fromAt": day.replace(hour=h, minute=m), "toAt": day.replace(hour=target, minute=10),
                                                  "beans": beans, "status": "redeemed", "propensity": 0.5,
                                                  "createdAt": day.replace(hour=max(0, h - 1)), "synthetic": True}))
                    else:
                        keep.append(m)
                        if rng.random() < 0.35:
                            arms[str(beans)]["offered"] += 1
                            writes.append(("nudge", {"uid": f"demo-guest-{rng.randint(1, 80)}", "cafeId": cafe_id,
                                                      "day": day.date().isoformat(), "context": "home",
                                                      "fromAt": day.replace(hour=h, minute=m), "toAt": day.replace(hour=min(22, h + 2), minute=10),
                                                      "beans": beans, "status": "declined", "propensity": 0.4,
                                                      "createdAt": day.replace(hour=max(0, h - 1)), "synthetic": True}))
                demand[h] = keep
        for h in range(24):
            load = len(demand[h])
            for m in demand[h]:
                placed = day.replace(hour=h, minute=m, second=rng.randint(0, 59), microsecond=0)
                wait = max(60, rng.gauss(150 + 22 * max(0, load - 8), 35))
                items = [rng.choice(drinks)] + ([rng.choice(menu)] if rng.random() < 0.45 else [])
                lines = [{"itemId": i["id"], "name": i["name"], "qty": 1, "modifiers": {}, "modifierLabels": [],
                          "unitPrice": i["price"], "lineTotal": i["price"], "lineId": f"s{k}"} for k, i in enumerate(items)]
                writes.append(("order", {"uid": f"demo-guest-{rng.randint(1, 80)}", "customerName": "Demo", "cafeId": cafe_id,
                                         "items": lines, "total": sum(l["lineTotal"] for l in lines), "status": "collected",
                                         "pickupCode": "DEM", "source": "demo", "createdAt": placed, "placedAt": placed,
                                         "startedAt": placed + timedelta(seconds=wait * 0.4),
                                         "readyAt": placed + timedelta(seconds=wait),
                                         "collectedAt": placed + timedelta(seconds=wait + 60),
                                         "payment": {"method": "upi", "status": "paid", "txnId": "DEMO-SIM"},
                                         "synthetic": True}))
    batch, n = db().batch(), 0
    counts = {"order": 0, "nudge": 0}
    for kind, doc in writes:
        batch.set(db().collection("orders" if kind == "order" else "nudges").document(), doc)
        counts[kind] += 1
        n += 1
        if n % 450 == 0:
            batch.commit()
            batch = db().batch()
    batch.commit()
    db().collection("cafes").document(cafe_id).collection("stats").document("nudges").set({"arms": arms})
    db().collection("cafes").document(cafe_id).set({"peakEngineSince": since, "demoData": True}, merge=True)
    menu_svc.invalidate(cafe_id)
    return {"orders": counts["order"], "nudges": counts["nudge"], "since": since.isoformat()}


def clear_demo(cafe_id: str) -> dict:
    removed = 0
    for col in ("orders", "nudges"):
        while True:
            docs = list(db().collection(col).where(filter=firestore.FieldFilter("cafeId", "==", cafe_id))
                        .where(filter=firestore.FieldFilter("synthetic", "==", True)).limit(400).stream())
            if not docs:
                break
            batch = db().batch()
            for d in docs:
                batch.delete(d.reference)
            batch.commit()
            removed += len(docs)
    ref = db().collection("cafes").document(cafe_id)
    if (ref.get().to_dict() or {}).get("demoData"):
        ref.update({"demoData": firestore.DELETE_FIELD, "peakEngineSince": firestore.DELETE_FIELD})
        ref.collection("stats").document("nudges").delete()
    menu_svc.invalidate(cafe_id)
    return {"removed": removed}
