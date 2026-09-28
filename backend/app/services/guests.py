"""
Guest profiles and segments for employees, plus targeted off-peak campaigns.

Staff see what helps them serve and target: first name, tier, visits, spend, usual
order, habitual time, diet/allergens and offer history. Email is shown to managers only.

Segments
  peak_regular  habitually orders inside a forecast peak (the people worth shifting)
  flexible      high propensity to shift (varied visit times, accepts offers)
  lapsing       3+ visits but none in the last 14 days
  vip           Reserve tier
  new           1-2 visits
"""

from datetime import datetime, timedelta

from fastapi import HTTPException
from google.cloud import firestore

from app.db import db, now
from app.services import loyalty, peak
from app.services import menu as menu_svc

SEGMENTS = ["peak_regular", "flexible", "lapsing", "vip", "new"]


def _mask(email: str) -> str:
    if "@" not in email:
        return ""
    name, domain = email.split("@", 1)
    return f"{name[:2]}***@{domain}"


def _peak_minutes(cafe_id: str) -> list[tuple[int, int]]:
    """Today's peak windows as (start, end) local minutes after midnight."""
    fc = peak.forecast(cafe_id)
    out = []
    for p in fc["peaks"]:
        s, e = datetime.fromisoformat(p["start"]), datetime.fromisoformat(p["end"])
        out.append((s.hour * 60 + s.minute, e.hour * 60 + e.minute))
    return out


def profile(uid: str, cafe_id: str, user: dict, peaks: list[tuple[int, int]] | None = None,
            manager: bool = False) -> dict:
    h = peak.habit(uid, cafe_id)
    loy = loyalty.summary(user)
    last = (user.get("loyalty") or {}).get("lastOrderAt")
    prefs = user.get("prefs") or {}
    score = peak.propensity(uid, user, h)
    habit_min = h["minute"] if h else None
    in_peak = bool(habit_min is not None and peaks and any(s <= habit_min < e for s, e in peaks))
    days_since = (now() - last).days if isinstance(last, datetime) else None

    segs = []
    if in_peak:
        segs.append("peak_regular")
    if score >= 0.55:
        segs.append("flexible")
    if loy["visits"] >= 3 and days_since is not None and days_since >= 14:
        segs.append("lapsing")
    if loy["tier"] == "Reserve":
        segs.append("vip")
    if 1 <= loy["visits"] <= 2:
        segs.append("new")

    return {
        "uid": uid,
        "name": (user.get("displayName") or "Guest").split(" ")[0],
        "email": user.get("email", "") if manager else _mask(user.get("email", "")),
        "tier": loy["tier"], "points": loy["points"], "visits": loy["visits"], "orders": loy["orders"],
        "lifetimeSpend": loy["lifetimeSpend"], "avgTicket": loy["avgTicket"],
        "lastOrderAt": loy["lastOrderAt"], "daysSinceLastOrder": days_since,
        "habitTime": f"{int(habit_min // 60):02d}:{int(habit_min % 60):02d}" if habit_min is not None else None,
        "habitSpreadMin": round(h["spread"]) if h else None,
        "shiftPropensity": score,
        "usual": (user.get("usuals") or [None])[0],
        "diet": prefs.get("diet", "any"), "avoid": prefs.get("avoid", []),
        "taste": {k: prefs.get(k) for k in ("temperature", "milk", "sweetness", "caffeine")},
        "segments": segs,
    }


def list_guests(cafe_id: str, segment: str | None, manager: bool, limit: int = 200) -> dict:
    peaks = _peak_minutes(cafe_id)
    guests = []
    for s in db().collection("users").where(filter=firestore.FieldFilter("role", "==", "customer")).limit(limit).stream():
        u = s.to_dict()
        if not (u.get("loyalty") or {}).get("orders"):
            continue
        g = profile(s.id, cafe_id, u, peaks, manager)
        if segment and segment not in g["segments"]:
            continue
        guests.append(g)
    guests.sort(key=lambda g: (g["lifetimeSpend"]), reverse=True)
    counts = {seg: 0 for seg in SEGMENTS}
    for g in guests if not segment else []:
        for seg in g["segments"]:
            counts[seg] += 1
    return {"guests": guests, "segmentCounts": counts if not segment else None,
            "peaks": [f"{s // 60:02d}:{s % 60:02d}-{e // 60:02d}:{e % 60:02d}" for s, e in peaks]}


def detail(cafe_id: str, uid: str, manager: bool) -> dict:
    snap = db().collection("users").document(uid).get()
    if not snap.exists:
        raise HTTPException(404, "Guest not found.")
    g = profile(uid, cafe_id, snap.to_dict(), _peak_minutes(cafe_id), manager)
    orders = []
    for s in (db().collection("orders").where(filter=firestore.FieldFilter("uid", "==", uid))
              .order_by("createdAt", direction=firestore.Query.DESCENDING).limit(10).stream()):
        o = s.to_dict()
        orders.append({"id": s.id, "at": o["createdAt"].isoformat(), "total": o["total"], "status": o["status"],
                       "items": [f"{l['qty']}x {l['name']}" for l in o.get("items", [])]})
    nudges = []
    for s in db().collection("nudges").where(filter=firestore.FieldFilter("uid", "==", uid)).limit(20).stream():
        n = s.to_dict()
        nudges.append({"day": n["day"], "beans": n["beans"], "status": n["status"], "context": n.get("context"),
                       "toAt": n["toAt"].isoformat()})
    nudges.sort(key=lambda n: n["day"], reverse=True)
    return {**g, "recentOrders": orders, "offers": nudges}


def campaign(cafe_id: str, segment: str, beans: int, staff_uid: str) -> dict:
    """Offer every guest in a segment a move from today's peak to the nearest quiet slot."""
    if segment not in SEGMENTS:
        raise HTTPException(400, "Unknown segment.")
    if beans not in (10, 20, 30, 40, 50):
        raise HTTPException(400, "Beans must be 10-50 in steps of 10.")
    cafe = menu_svc.get_cafe(cafe_id)
    zone = menu_svc.tz(cafe)
    t = now()
    day = t.astimezone(zone).date().isoformat()
    fc = peak.forecast(cafe_id)
    upcoming = [p for p in fc["peaks"] if datetime.fromisoformat(p["end"]) > t]
    if not upcoming:
        raise HTTPException(409, "No rush left in today's forecast, so there's nothing to shift.")
    p0 = upcoming[0]
    peak_at = max(datetime.fromisoformat(p0["start"]), t + timedelta(minutes=20))
    sent = skipped = 0
    batch = db().batch()
    for g in list_guests(cafe_id, segment, manager=False)["guests"]:
        if peak._existing(g["uid"], cafe_id, day):
            skipped += 1
            continue
        # Aim at the guest's own habit if it sits in the peak, otherwise the peak start.
        at = peak_at
        if g["habitTime"]:
            hh, mm = map(int, g["habitTime"].split(":"))
            candidate = t.astimezone(zone).replace(hour=hh, minute=mm, second=0, microsecond=0)
            if candidate > t and peak._slot_at(fc, candidate) and peak._slot_at(fc, candidate)["kind"] == "peak":
                at = candidate
        to_at = peak._quiet_alternative(fc, at)
        if not to_at:
            skipped += 1
            continue
        batch.set(db().collection("nudges").document(), {
            "uid": g["uid"], "cafeId": cafe_id, "day": day, "context": "campaign", "segment": segment,
            "fromAt": at, "toAt": to_at, "fromWaitSec": (peak._slot_at(fc, at) or {}).get("expectedWaitSec"),
            "toWaitSec": (peak._slot_at(fc, to_at) or {}).get("expectedWaitSec"),
            "beans": beans, "propensity": g["shiftPropensity"], "status": "offered",
            "createdAt": t, "expiresAt": min(t + timedelta(hours=6), to_at), "sentBy": staff_uid})
        sent += 1
    batch.commit()
    if sent:
        db().collection("cafes").document(cafe_id).set({"peakEngineSince": cafe.get("peakEngineSince") or t}, merge=True)
        menu_svc.invalidate(cafe_id)
    return {"sent": sent, "skipped": skipped, "peak": p0}


def order_snapshot(user: dict) -> dict:
    """Short guest note printed on the barista board card."""
    loy = loyalty.summary(user)
    prefs = user.get("prefs") or {}
    return {"tier": loy["tier"], "visits": loy["visits"], "diet": prefs.get("diet", "any"),
            "avoid": prefs.get("avoid", []), "firstVisit": loy["visits"] == 0}
