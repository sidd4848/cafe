"""
Busyness profile and "best time to visit".

`cafes/{id}/busyness/{dow}` (dow 0 = Monday) holds 24 hourly cells of
{orders, avgWaitSec}. A new cafe has no history, so the seed writes a prior shaped like a
typical Indian specialty café (morning commute, lunch, evening peaks, busier weekends).
The nightly job blends real orders from the last 8 weeks into that prior, weighting the
real data more as it accumulates, so the curve converges on what actually happens.
"""

import math
from collections import defaultdict
from datetime import datetime, timedelta

from google.cloud import firestore

from app.db import db, now
from app.services import menu as menu_svc

WEEKS = 8
FULL_TRUST_ORDERS = 600
BASE_WAIT = 150


def _bump(h: float, centre: float, width: float, height: float) -> float:
    return height * math.exp(-((h - centre) ** 2) / (2 * width ** 2))


def prior_hourly(dow: int) -> list[dict]:
    weekend = dow >= 5
    cells = []
    for h in range(24):
        if h < 8 or h >= 23:
            cells.append({"orders": 0.0, "avgWaitSec": 0.0})
            continue
        x = h + 0.5
        orders = 4 + _bump(x, 9.5, 1.2, 10 if not weekend else 5) \
                   + _bump(x, 13.5, 1.3, 9) \
                   + _bump(x, 18, 1.8, 12 if not weekend else 18) \
                   + (_bump(x, 12, 2.5, 8) if weekend else 0)
        wait = BASE_WAIT + 22 * max(0.0, orders - 8)
        cells.append({"orders": round(orders, 1), "avgWaitSec": round(wait)})
    return cells


def seed_prior(cafe_id: str) -> None:
    ref = db().collection("cafes").document(cafe_id).collection("busyness")
    for dow in range(7):
        prior = prior_hourly(dow)
        ref.document(str(dow)).set({"prior": prior, "hourly": prior, "realOrders": 0,
                                    "updatedAt": now()})


def rebuild(cafe_id: str) -> dict:
    cafe = menu_svc.get_cafe(cafe_id)
    zone = menu_svc.tz(cafe)
    since = now() - timedelta(weeks=WEEKS)
    counts = defaultdict(float)
    waits = defaultdict(list)
    total = 0
    for s in (db().collection("orders")
              .where(filter=firestore.FieldFilter("cafeId", "==", cafe_id))
              .where(filter=firestore.FieldFilter("placedAt", ">=", since)).stream()):
        o = s.to_dict()
        placed = o.get("placedAt")
        if not isinstance(placed, datetime) or o.get("status") == "cancelled":
            continue
        local = placed.astimezone(zone)
        key = (local.weekday(), local.hour)
        counts[key] += 1
        total += 1
        ready = o.get("readyAt")
        if isinstance(ready, datetime):
            waits[key].append((ready - placed).total_seconds())

    w = min(1.0, total / FULL_TRUST_ORDERS)
    ref = db().collection("cafes").document(cafe_id).collection("busyness")
    for dow in range(7):
        snap = ref.document(str(dow)).get()
        prior = (snap.to_dict() or {}).get("prior") if snap.exists else None
        prior = prior or prior_hourly(dow)
        hourly = []
        for h in range(24):
            real_orders = counts[(dow, h)] / WEEKS
            real_wait = sum(waits[(dow, h)]) / len(waits[(dow, h)]) if waits[(dow, h)] else prior[h]["avgWaitSec"]
            hourly.append({
                "orders": round(w * real_orders + (1 - w) * prior[h]["orders"], 1),
                "avgWaitSec": round(w * real_wait + (1 - w) * prior[h]["avgWaitSec"]),
            })
        ref.document(str(dow)).set({"prior": prior, "hourly": hourly, "realOrders": total,
                                    "realWeight": round(w, 2), "updatedAt": now()})
    return {"realOrders": total, "realWeight": w}


def _level(wait: float) -> str:
    return "quiet" if wait < 240 else "moderate" if wait < 420 else "busy"


def best_times(cafe_id: str, date_local: str | None = None) -> dict:
    """30-minute slots across opening hours with expected wait, plus the quietest ones."""
    cafe = menu_svc.get_cafe(cafe_id)
    zone = menu_svc.tz(cafe)
    t = now()
    local_now = t.astimezone(zone)
    day = (datetime.fromisoformat(date_local).replace(tzinfo=zone)
           if date_local else local_now)
    is_today = day.date() == local_now.date()
    snap = db().collection("cafes").document(cafe_id).collection("busyness").document(str(day.weekday())).get()
    hourly = (snap.to_dict() or {}).get("hourly") if snap.exists else None
    hourly = hourly or prior_hourly(day.weekday())

    # Today, lean on what the queue is actually doing: scale the next couple of hours by
    # how far live wait sits from the profile, fading back to the profile after that.
    live_ratio = 1.0
    if is_today:
        live = db().collection("cafes").document(cafe_id).collection("stats").document("live").get()
        current = float((live.to_dict() or {}).get("currentWaitSec", 0)) if live.exists else 0
        expected_now = hourly[local_now.hour]["avgWaitSec"] or BASE_WAIT
        if current:
            live_ratio = max(0.4, min(3.0, current / expected_now))

    open_at, close_at = menu_svc.opening_window(cafe, day)
    slots = []
    slot = open_at
    while slot < close_at:
        cell = hourly[slot.hour]
        wait = cell["avgWaitSec"]
        if is_today:
            hours_ahead = (slot - local_now).total_seconds() / 3600
            if hours_ahead < -0.5:
                slot += timedelta(minutes=30)
                continue
            fade = math.exp(-max(0.0, hours_ahead) / 1.5)
            wait = wait * (1 + (live_ratio - 1) * fade)
        slots.append({"start": slot.isoformat(), "expectedWaitSec": round(wait),
                      "orders": cell["orders"], "level": _level(wait)})
        slot += timedelta(minutes=30)

    upcoming = [s for s in slots if datetime.fromisoformat(s["start"]) >= local_now - timedelta(minutes=30)]
    best = sorted(upcoming, key=lambda s: s["expectedWaitSec"])[:3]
    return {"date": day.date().isoformat(), "timezone": str(zone), "slots": slots,
            "best": sorted(best, key=lambda s: s["start"]), "liveAdjustment": round(live_ratio, 2)}
