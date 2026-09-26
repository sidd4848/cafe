"""
Dine-in floor: tables, walk-in / digital waitlist, predicted table waits, smart seating.

Table wait model (floor-v1)
---------------------------
* Dwell time (seated -> cleared) is learned per party-size bucket as an EWMA from real
  table turns, the "historical checkout pattern". Seeds: 45 / 60 / 75 min.
* Each table that fits the party becomes free at:
      free now                    -> now
      needs clearing ("dirty")    -> now + turnover (~3 min)
      seated                      -> seatedAt + dwell(their bucket), never before now + 2 min
* Parties already waiting are given tables first, greedily in queue order (best-fit
  table, earliest free), pushing that table's next-free time out by their own dwell.
  The quote for a new party is when the earliest fitting table frees after that.

Smart seating
-------------
For a waiting party the suggested table is the free table that wastes the fewest seats
(a pair shouldn't take a 6-top while a 6 waits), honouring a bar/no-bar preference, and
the suggested server is the one on shift with the fewest occupied tables (tie: whoever
was seated least recently), so work stays balanced and service stays attentive.
"""

import hashlib
import hmac
from datetime import datetime, timedelta

from fastapi import HTTPException
from google.cloud import firestore

from app.db import db, now
from app.services import connect as connect_svc
from app.services import menu as menu_svc

ALPHA = 0.2
MIN_REMAINING = timedelta(minutes=2)


def _bucket(size: int) -> str:
    return "small" if size <= 2 else "medium" if size <= 4 else "large"


def _cafe_ref(cafe_id: str):
    return db().collection("cafes").document(cafe_id)


def floor_stats(cafe_id: str) -> dict:
    snap = _cafe_ref(cafe_id).collection("stats").document("floor").get()
    d = snap.to_dict() if snap.exists else {}
    return {"dwellSec": d.get("dwellSec") or {"small": 2700, "medium": 3600, "large": 4500},
            "turnoverSec": d.get("turnoverSec", 180)}


def tables(cafe_id: str) -> list[dict]:
    return [{"id": s.id, **s.to_dict()} for s in _cafe_ref(cafe_id).collection("tables").stream()]


def waitlist(cafe_id: str) -> list[dict]:
    snaps = (_cafe_ref(cafe_id).collection("waitlist")
             .where(filter=firestore.FieldFilter("status", "==", "waiting")).stream())
    return sorted(({"id": s.id, **s.to_dict()} for s in snaps), key=lambda p: p["joinedAt"])


def servers(cafe_id: str) -> list[dict]:
    snaps = (_cafe_ref(cafe_id).collection("shift")
             .where(filter=firestore.FieldFilter("onShift", "==", True)).stream())
    return [{"uid": s.id, **s.to_dict()} for s in snaps]


def _fits(table: dict, party: dict) -> bool:
    if table["seats"] < party["size"]:
        return False
    if party.get("seating") == "no_bar" and table["zone"] == "bar":
        return False
    if party.get("seating") == "bar" and table["zone"] != "bar":
        return False
    return True


def _free_at(table: dict, stats: dict, t: datetime) -> datetime:
    if table["status"] == "free":
        return t
    if table["status"] == "dirty":
        return t + timedelta(seconds=stats["turnoverSec"])
    seated = table.get("seatedAt") or t
    dwell = stats["dwellSec"][_bucket(int(table.get("partySize") or table["seats"]))]
    return max(seated + timedelta(seconds=dwell), t + MIN_REMAINING)


def _simulate(cafe_id: str, parties: list[dict]) -> dict[str, float]:
    """Queue the given parties (in order) onto tables. Returns partyId -> wait seconds."""
    t = now()
    stats = floor_stats(cafe_id)
    avail = {tb["id"]: (tb, _free_at(tb, stats, t)) for tb in tables(cafe_id)}
    quotes: dict[str, float] = {}
    for p in parties:
        options = [(free, tb["seats"] - p["size"], tid) for tid, (tb, free) in avail.items() if _fits(tb, p)]
        if not options:
            quotes[p["id"]] = -1  # no table big enough; staff will need to combine tables
            continue
        free, _, tid = min(options)
        quotes[p["id"]] = max(0.0, (free - t).total_seconds())
        tb = avail[tid][0]
        avail[tid] = (tb, free + timedelta(seconds=stats["dwellSec"][_bucket(p["size"])]))
    return quotes


def quote(cafe_id: str, size: int, seating: str = "any") -> dict:
    queue = waitlist(cafe_id)
    probe = {"id": "_probe", "size": size, "seating": seating}
    quotes = _simulate(cafe_id, queue + [probe])
    free_now = sum(1 for tb in tables(cafe_id) if tb["status"] == "free" and _fits(tb, probe))
    return {"partySize": size, "quotedWaitSec": round(quotes["_probe"]), "freeNow": free_now,
            "waitingParties": len(queue), "modelVersion": "floor-v1"}


def requote_all(cafe_id: str) -> None:
    queue = waitlist(cafe_id)
    if not queue:
        return
    quotes = _simulate(cafe_id, queue)
    t = now()
    batch = db().batch()
    col = _cafe_ref(cafe_id).collection("waitlist")
    for i, p in enumerate(queue):
        q = quotes[p["id"]]
        batch.update(col.document(p["id"]), {
            "position": i + 1, "quotedWaitSec": round(q),
            "estimatedSeatAt": t + timedelta(seconds=max(0, q)) if q >= 0 else None, "quotedAt": t})
    batch.commit()


# ---- Waitlist -------------------------------------------------------------------------

def join(cafe_id: str, uid: str | None, name: str, size: int, seating: str, source: str) -> dict:
    if not 1 <= size <= 12:
        raise HTTPException(400, "Party size must be 1-12.")
    if uid:
        for p in waitlist(cafe_id):
            if p.get("uid") == uid:
                raise HTTPException(409, "You're already on the waitlist.")
    t = now()
    ref = _cafe_ref(cafe_id).collection("waitlist").document()
    ref.set({"uid": uid, "name": name[:40] or "Guest", "size": size, "seating": seating,
             "status": "waiting", "joinedAt": t, "source": source,
             "expiresAt": t + timedelta(days=2)})
    requote_all(cafe_id)
    return {"id": ref.id, **(ref.get().to_dict() or {})}


def my_entry(cafe_id: str, uid: str) -> dict | None:
    for s in (_cafe_ref(cafe_id).collection("waitlist")
              .where(filter=firestore.FieldFilter("uid", "==", uid)).stream()):
        p = s.to_dict()
        if p["status"] in {"waiting", "seated"} and p["joinedAt"] > now() - timedelta(hours=6):
            return {"id": s.id, **p}
    return None


def leave(cafe_id: str, party_id: str, uid: str | None = None) -> None:
    ref = _cafe_ref(cafe_id).collection("waitlist").document(party_id)
    snap = ref.get()
    if not snap.exists or (uid and snap.get("uid") != uid):
        raise HTTPException(404, "Not on the waitlist.")
    ref.update({"status": "left", "leftAt": now()})
    requote_all(cafe_id)


# ---- Smart seating --------------------------------------------------------------------

def suggestions(cafe_id: str) -> list[dict]:
    """Best free table and server for each waiting party, without double-booking a table."""
    tbs = tables(cafe_id)
    free = [tb for tb in tbs if tb["status"] == "free"]
    load = {s["uid"]: {**s, "active": 0} for s in servers(cafe_id)}
    for tb in tbs:
        if tb["status"] == "seated" and tb.get("serverUid") in load:
            load[tb["serverUid"]]["active"] += 1
    used: set[str] = set()
    out = []
    for p in waitlist(cafe_id):
        options = sorted((tb for tb in free if tb["id"] not in used and _fits(tb, p)),
                         key=lambda tb: (tb["seats"] - p["size"], tb["zone"] == "bar" and p["size"] > 1))
        table = options[0] if options else None
        server = min(load.values(), key=lambda s: (s["active"], s.get("lastSeatedAt") or datetime.min.replace(tzinfo=now().tzinfo)),
                     default=None)
        if table:
            used.add(table["id"])
            if server:
                load[server["uid"]]["active"] += 1
        out.append({"partyId": p["id"], "tableId": table["id"] if table else None,
                    "serverUid": server["uid"] if server and table else None,
                    "wastedSeats": table["seats"] - p["size"] if table else None})
    return out


def seat(cafe_id: str, table_id: str, party_id: str | None, size: int | None, server_uid: str | None,
         staff_uid: str) -> dict:
    t = now()
    tref = _cafe_ref(cafe_id).collection("tables").document(table_id)
    tb = tref.get()
    if not tb.exists:
        raise HTTPException(404, "Table not found.")
    if tb.get("status") != "free":
        raise HTTPException(409, "That table isn't free.")
    name = "Walk-in"
    if party_id:
        pref = _cafe_ref(cafe_id).collection("waitlist").document(party_id)
        p = pref.get()
        if not p.exists or p.get("status") != "waiting":
            raise HTTPException(409, "That party isn't waiting.")
        size, name = p.get("size"), p.get("name")
        pref.update({"status": "seated", "seatedAt": t, "tableId": table_id, "serverUid": server_uid})
    if not size:
        raise HTTPException(400, "Party size required for a walk-in.")
    server_name = None
    if server_uid:
        sref = _cafe_ref(cafe_id).collection("shift").document(server_uid)
        s = sref.get()
        if s.exists:
            server_name = s.get("name")
            sref.update({"lastSeatedAt": t})
    tref.update({"status": "seated", "seatedAt": t, "partySize": size, "partyName": name,
                 "partyId": party_id, "serverUid": server_uid, "serverName": server_name, "seatedBy": staff_uid})
    requote_all(cafe_id)
    return {"ok": True}


def clear(cafe_id: str, table_id: str) -> dict:
    """Guests left: learn the dwell time, mark the table for bussing."""
    tref = _cafe_ref(cafe_id).collection("tables").document(table_id)
    tb = tref.get().to_dict() or {}
    if tb.get("status") != "seated":
        raise HTTPException(409, "Table isn't seated.")
    t = now()
    seated = tb.get("seatedAt")
    if isinstance(seated, datetime):
        observed = (t - seated).total_seconds()
        if 5 * 60 <= observed <= 5 * 3600:
            stats = floor_stats(cafe_id)
            b = _bucket(int(tb.get("partySize") or tb["seats"]))
            stats["dwellSec"][b] = round((1 - ALPHA) * stats["dwellSec"][b] + ALPHA * observed)
            _cafe_ref(cafe_id).collection("stats").document("floor").set({"dwellSec": stats["dwellSec"]}, merge=True)
    tref.update({"status": "dirty", "clearedAt": t, "partyId": None, "partyName": None,
                 "partySize": None, "serverUid": None, "serverName": None})
    requote_all(cafe_id)
    return {"ok": True}


def mark_ready(cafe_id: str, table_id: str) -> dict:
    tref = _cafe_ref(cafe_id).collection("tables").document(table_id)
    if (tref.get().to_dict() or {}).get("status") != "dirty":
        raise HTTPException(409, "Table isn't waiting to be cleared.")
    tref.update({"status": "free"})
    requote_all(cafe_id)
    return {"ok": True}


def set_shift(cafe_id: str, uid: str, name: str, on: bool) -> dict:
    _cafe_ref(cafe_id).collection("shift").document(uid).set(
        {"name": name, "onShift": on, "since": now()}, merge=True)
    return {"onShift": on}


# ---- Table QR -------------------------------------------------------------------------

def table_token(cafe_id: str, table_id: str, day: str | None = None) -> str:
    cafe = menu_svc.get_cafe(cafe_id)
    day = day or now().astimezone(menu_svc.tz(cafe)).date().isoformat()
    secret = connect_svc._qr_secret(cafe_id)
    return hmac.new(secret, f"{cafe_id}:table:{table_id}:{day}".encode(), hashlib.sha256).hexdigest()[:20]


def verify_table(cafe_id: str, table_id: str, token: str) -> dict:
    snap = _cafe_ref(cafe_id).collection("tables").document(table_id).get()
    if not snap.exists or not hmac.compare_digest(token or "", table_token(cafe_id, table_id)):
        raise HTTPException(400, "This table code has expired. Scan the QR on your table again.")
    return {"id": snap.id, **snap.to_dict()}
