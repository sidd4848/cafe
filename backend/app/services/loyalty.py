"""
Smart loyalty profile: points ("beans"), tier, visits and spending habits.

1 bean per Rs 10 paid. A visit is a distinct café-local day with at least one order.
`avgTicket` feeds the recommender's price-comfort term, so a guest who usually spends
Rs 250 isn't pushed toward Rs 400 frappés, and vice versa.
"""

from datetime import datetime

from google.cloud import firestore

from app.db import db, now

TIERS = [("Bean", 0), ("Roast", 250), ("Reserve", 800)]
PERKS = {
    "Bean": ["Birthday drink on us"],
    "Roast": ["Free extra shot or plant milk", "Birthday drink on us"],
    "Reserve": ["Free extra shot or plant milk", "Monthly single-origin tasting", "Priority pre-order release"],
}


def tier_for(points: int) -> tuple[str, str | None, int]:
    current = TIERS[0][0]
    nxt, to_next = None, 0
    for i, (name, threshold) in enumerate(TIERS):
        if points >= threshold:
            current = name
            if i + 1 < len(TIERS):
                nxt, to_next = TIERS[i + 1][0], TIERS[i + 1][1] - points
            else:
                nxt, to_next = None, 0
    return current, nxt, to_next


def record_order(uid: str, total_paise: int, local_day: str) -> None:
    ref = db().collection("users").document(uid)
    snap = ref.get()
    loyalty = dict((snap.to_dict() or {}).get("loyalty") or {}) if snap.exists else {}
    days = list(loyalty.get("recentDays", []))
    orders = int(loyalty.get("orders", 0)) + 1
    spend = int(loyalty.get("lifetimeSpend", 0)) + total_paise
    visits = int(loyalty.get("visits", 0))
    if local_day not in days:
        visits += 1
        days = (days + [local_day])[-30:]
    loyalty.update({
        "points": int(loyalty.get("points", 0)) + total_paise // 1000,
        "orders": orders, "visits": visits, "lifetimeSpend": spend,
        "avgTicket": spend // orders, "recentDays": days, "lastOrderAt": now(),
    })
    ref.set({"loyalty": loyalty}, merge=True)


def refund(uid: str, total_paise: int) -> None:
    ref = db().collection("users").document(uid)
    snap = ref.get()
    loyalty = dict((snap.to_dict() or {}).get("loyalty") or {}) if snap.exists else {}
    if not loyalty:
        return
    loyalty["points"] = max(0, int(loyalty.get("points", 0)) - total_paise // 1000)
    loyalty["lifetimeSpend"] = max(0, int(loyalty.get("lifetimeSpend", 0)) - total_paise)
    ref.set({"loyalty": loyalty}, merge=True)


def bonus(uid: str, beans: int) -> None:
    """Award extra beans (e.g. for shifting a visit out of the rush)."""
    db().collection("users").document(uid).set(
        {"loyalty": {"points": firestore.Increment(beans), "bonusBeans": firestore.Increment(beans)}}, merge=True)


def summary(user: dict) -> dict:
    loyalty = user.get("loyalty") or {}
    points = int(loyalty.get("points", 0))
    tier, nxt, to_next = tier_for(points)
    last = loyalty.get("lastOrderAt")
    return {
        "points": points, "tier": tier, "nextTier": nxt, "pointsToNext": to_next,
        "visits": int(loyalty.get("visits", 0)), "orders": int(loyalty.get("orders", 0)),
        "lifetimeSpend": int(loyalty.get("lifetimeSpend", 0)), "avgTicket": int(loyalty.get("avgTicket", 0)),
        "lastOrderAt": last.isoformat() if isinstance(last, datetime) else None,
        "perks": PERKS[tier],
    }
