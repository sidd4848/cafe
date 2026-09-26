"""
Connect: meet people at the café.

Flow: opt in with a small profile -> check in by scanning the table QR -> see others who
are visible and checked in -> send a "spark" with an AI icebreaker -> if accepted, a
connection opens with a 24-hour window to chat and set up a meetup -> both confirm the
meetup and the connection is kept (`met`); otherwise it expires and is deleted 7 days
later by Firestore TTL.

Privacy: presence and profiles are never readable by clients directly. Only this module
lists people, and only to someone who is visible and checked in at the same café,
excluding blocks in both directions.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from google.cloud import firestore

from app.db import db, now
from app.services import llm
from app.services import menu as menu_svc

logger = logging.getLogger(__name__)

PRESENCE_TTL = timedelta(hours=3)
SPARK_TTL = timedelta(hours=2)
WINDOW = timedelta(hours=24)
GRACE = timedelta(days=7)
SPARKS_PER_HOUR = 5
SPARKS_PER_DAY = 20

INTERESTS = [
    "coffee brewing", "startups", "design", "books", "music", "gaming", "fitness", "running",
    "photography", "travel", "films", "art", "coding", "ai", "language exchange", "board games",
    "writing", "food", "hiking", "cricket", "football", "yoga", "podcasts", "investing",
]
OPEN_TO = ["chat", "cowork", "language_exchange", "board_games", "networking", "coffee_nerding"]


# ---- QR check-in token -----------------------------------------------------------------

def _qr_secret(cafe_id: str) -> bytes:
    ref = db().collection("cafePrivate").document(cafe_id)
    snap = ref.get()
    secret = (snap.to_dict() or {}).get("qrSecret") if snap.exists else None
    if not secret:
        secret = secrets.token_hex(32)
        ref.set({"qrSecret": secret}, merge=True)
    return secret.encode()


def checkin_token(cafe_id: str, day: str) -> str:
    """Rotates daily (cafe-local date). A photo of yesterday's QR stops working."""
    return hmac.new(_qr_secret(cafe_id), f"{cafe_id}:{day}".encode(), hashlib.sha256).hexdigest()[:20]


def today_token(cafe_id: str) -> str:
    cafe = menu_svc.get_cafe(cafe_id)
    return checkin_token(cafe_id, now().astimezone(menu_svc.tz(cafe)).date().isoformat())


# ---- Helpers ---------------------------------------------------------------------------

def _blocked_pair(a: str, b: str) -> bool:
    users = db().collection("blocks")
    return (users.document(a).collection("blocked").document(b).get().exists
            or users.document(b).collection("blocked").document(a).get().exists)


def _blocked_set(uid: str) -> set[str]:
    mine = {s.id for s in db().collection("blocks").document(uid).collection("blocked").stream()}
    theirs = {s.reference.parent.parent.id for s in db().collection_group("blocked")
              .where(filter=firestore.FieldFilter("uid", "==", uid)).stream()}
    return mine | theirs


def get_profile(uid: str) -> dict | None:
    snap = db().collection("connectProfiles").document(uid).get()
    return snap.to_dict() if snap.exists else None


def _presence(cafe_id: str, uid: str) -> dict | None:
    snap = db().collection("presence").document(f"{cafe_id}_{uid}").get()
    if not snap.exists:
        return None
    p = snap.to_dict()
    return p if p.get("expiresAt") and p["expiresAt"] > now() else None


def _public(uid: str, profile: dict) -> dict:
    return {"uid": uid, "firstName": profile.get("firstName"), "bio": profile.get("bio", ""),
            "interests": profile.get("interests", []), "openTo": profile.get("openTo", [])}


# ---- Profile & presence ----------------------------------------------------------------

def upsert_profile(uid: str, data: dict) -> dict:
    first = (data.get("firstName") or "").strip().split(" ")[0][:24]
    bio = (data.get("bio") or "").strip()[:140]
    interests = [i for i in (data.get("interests") or []) if isinstance(i, str)][:8]
    open_to = [o for o in (data.get("openTo") or []) if o in OPEN_TO]
    visible = bool(data.get("visible"))
    if visible and not data.get("ageConfirmed18"):
        raise HTTPException(400, "Confirm you're 18 or older to be visible.")
    if not first:
        raise HTTPException(400, "A first name is required.")
    ok, reason = llm.moderate(f"Name: {first}\nBio: {bio}\nInterests: {', '.join(interests)}")
    if not ok:
        raise HTTPException(400, reason or "Please revise your profile.")
    profile = {"firstName": first, "bio": bio, "interests": interests, "openTo": open_to,
               "visible": visible, "ageConfirmed18": bool(data.get("ageConfirmed18")),
               "updatedAt": now()}
    db().collection("connectProfiles").document(uid).set(profile, merge=True)
    if not visible:
        for s in db().collection("presence").where(filter=firestore.FieldFilter("uid", "==", uid)).stream():
            s.reference.delete()
    return profile


def check_in(uid: str, cafe_id: str, token: str, mood: str = "", table_id: str | None = None) -> dict:
    cafe = menu_svc.get_cafe(cafe_id)
    if not cafe.get("connectEnabled"):
        raise HTTPException(403, "Connect isn't enabled at this café.")
    if table_id:
        from app.services import floor  # table QR codes double as Connect check-in
        floor.verify_table(cafe_id, table_id, token)
    elif not hmac.compare_digest(token or "", today_token(cafe_id)):
        raise HTTPException(400, "This QR code has expired. Scan the one on your table.")
    profile = get_profile(uid)
    if not profile or not profile.get("visible"):
        raise HTTPException(400, "Set up your Connect profile and turn on visibility first.")
    t = now()
    doc = {"uid": uid, "cafeId": cafe_id, "checkedInAt": t, "mood": (mood or "")[:60],
           "expiresAt": t + PRESENCE_TTL}
    db().collection("presence").document(f"{cafe_id}_{uid}").set(doc)
    return {"cafeId": cafe_id, "checkedInAt": t.isoformat(), "expiresAt": doc["expiresAt"].isoformat()}


def check_out(uid: str, cafe_id: str) -> None:
    db().collection("presence").document(f"{cafe_id}_{uid}").delete()


def status(uid: str) -> dict:
    """Where the caller is checked in, if anywhere."""
    for s in db().collection("presence").where(filter=firestore.FieldFilter("uid", "==", uid)).stream():
        p = s.to_dict()
        if p.get("expiresAt") and p["expiresAt"] > now():
            return {"cafeId": p["cafeId"], "checkedInAt": p["checkedInAt"].isoformat(),
                    "expiresAt": p["expiresAt"].isoformat(), "mood": p.get("mood", "")}
    return {}


def people_here(uid: str, cafe_id: str) -> list[dict]:
    me = get_profile(uid)
    if not me or not me.get("visible") or not _presence(cafe_id, uid):
        raise HTTPException(403, "Check in at this café to see who's here.")
    blocked = _blocked_set(uid)
    t = now()
    mine = set(me.get("interests", []))
    my_open = set(me.get("openTo", []))
    out = []
    for s in db().collection("presence").where(filter=firestore.FieldFilter("cafeId", "==", cafe_id)).stream():
        p = s.to_dict()
        other = p["uid"]
        if other == uid or other in blocked or not p.get("expiresAt") or p["expiresAt"] <= t:
            continue
        prof = get_profile(other)
        if not prof or not prof.get("visible"):
            continue
        theirs = set(prof.get("interests", []))
        shared = sorted(mine & theirs)
        union = mine | theirs
        score = (len(shared) / len(union) if union else 0) + 0.2 * len(my_open & set(prof.get("openTo", [])))
        out.append({**_public(other, prof), "mood": p.get("mood", ""),
                    "sharedInterests": shared, "matchScore": round(score, 2),
                    "checkedInAt": p["checkedInAt"].isoformat()})
    return sorted(out, key=lambda x: x["matchScore"], reverse=True)


# ---- Icebreakers -----------------------------------------------------------------------

_ICE_SCHEMA = {"type": "OBJECT", "properties": {"lines": {"type": "ARRAY", "items": {"type": "STRING"}}},
               "required": ["lines"]}


def icebreakers(a: dict, b: dict, cafe_name: str, n: int = 3) -> list[str]:
    shared = sorted(set(a.get("interests", [])) & set(b.get("interests", [])))
    prompt = (
        f"Two people are at {cafe_name}.\n"
        f"Person A: {a.get('firstName')}. Bio: {a.get('bio') or '-'}. Interests: {', '.join(a.get('interests', []))}. Open to: {', '.join(a.get('openTo', []))}\n"
        f"Person B: {b.get('firstName')}. Bio: {b.get('bio') or '-'}. Interests: {', '.join(b.get('interests', []))}. Open to: {', '.join(b.get('openTo', []))}\n"
        f"Shared interests: {', '.join(shared) or 'none obvious'}.\n"
        f"Write {n} short, specific, friendly opening lines Person A could send Person B (max 22 words each). "
        "Reference a shared interest or something in B's bio. Light, respectful, not flirty, no emojis, no pickup lines."
    )
    try:
        lines = llm.generate_json("You help strangers start a friendly conversation in a café.",
                                  prompt, _ICE_SCHEMA, 0.9).get("lines", [])
        lines = [l.strip() for l in lines if l.strip()][:n]
        if lines:
            return lines
    except Exception as e:
        logger.warning(f"Icebreaker generation failed: {e}")
    topic = shared[0] if shared else "what brings you here"
    return [f"Hi {b.get('firstName')}! I noticed we both like {topic}. What got you into it?"
            if shared else f"Hi {b.get('firstName')}! What are you drinking today? I'm looking for a new favourite."]


def draft_spark(uid: str, to_uid: str, cafe_id: str) -> dict:
    me, them = get_profile(uid), get_profile(to_uid)
    if not me or not them or not them.get("visible"):
        raise HTTPException(404, "That person isn't available.")
    cafe = menu_svc.get_cafe(cafe_id)
    return {"suggestions": icebreakers(me, them, cafe["name"], 3)}


# ---- Sparks ----------------------------------------------------------------------------

def send_spark(uid: str, to_uid: str, cafe_id: str, note: str) -> dict:
    if uid == to_uid:
        raise HTTPException(400, "You can't spark yourself.")
    if not _presence(cafe_id, uid) or not _presence(cafe_id, to_uid):
        raise HTTPException(400, "You both need to be checked in here.")
    if _blocked_pair(uid, to_uid):
        raise HTTPException(404, "That person isn't available.")
    t = now()
    sparks = db().collection("sparks")
    recent = [s.to_dict() for s in sparks.where(filter=firestore.FieldFilter("fromUid", "==", uid))
              .where(filter=firestore.FieldFilter("createdAt", ">=", t - timedelta(days=1))).stream()]
    if len(recent) >= SPARKS_PER_DAY or \
            sum(1 for r in recent if r["createdAt"] >= t - timedelta(hours=1)) >= SPARKS_PER_HOUR:
        raise HTTPException(429, "You've sent a lot of sparks. Try again a bit later.")
    if any(r["toUid"] == to_uid and r["status"] == "pending" for r in recent):
        raise HTTPException(409, "You already have a pending spark with them.")

    note = (note or "").strip()[:280]
    if not note:
        raise HTTPException(400, "Add a message to your spark.")
    ok, reason = llm.moderate(note)
    if not ok:
        raise HTTPException(400, reason)
    me, them = get_profile(uid), get_profile(to_uid)
    doc = {
        "fromUid": uid, "toUid": to_uid, "cafeId": cafe_id, "note": note,
        "from": _public(uid, me), "to": _public(to_uid, them),
        "sharedInterests": sorted(set(me.get("interests", [])) & set(them.get("interests", []))),
        "status": "pending", "createdAt": t, "expiresAt": t + SPARK_TTL,
    }
    ref = sparks.document()
    ref.set(doc)
    return {"id": ref.id, "status": "pending"}


def respond_spark(uid: str, spark_id: str, accept: bool) -> dict:
    ref = db().collection("sparks").document(spark_id)
    snap = ref.get()
    if not snap.exists or snap.get("toUid") != uid:
        raise HTTPException(404, "Spark not found.")
    spark = snap.to_dict()
    t = now()
    if spark["status"] != "pending" or spark["expiresAt"] <= t:
        raise HTTPException(409, "This spark has already closed.")
    if not accept:
        ref.update({"status": "declined", "respondedAt": t})
        return {"status": "declined"}
    if _blocked_pair(uid, spark["fromUid"]):
        raise HTTPException(404, "That person isn't available.")

    cafe = menu_svc.get_cafe(spark["cafeId"])
    a, b = get_profile(spark["fromUid"]), get_profile(uid)
    conn_ref = db().collection("connections").document()
    conn = {
        "members": sorted([spark["fromUid"], uid]),
        "profiles": {spark["fromUid"]: _public(spark["fromUid"], a), uid: _public(uid, b)},
        "cafeId": spark["cafeId"], "cafeName": cafe["name"], "sparkId": spark_id,
        "openedAt": t, "windowEndsAt": t + WINDOW, "status": "open",
        "meetup": None, "icebreakers": icebreakers(b, a, cafe["name"], 3),
        "expiresAt": t + WINDOW + GRACE,
    }
    batch = db().batch()
    batch.set(conn_ref, conn)
    batch.update(ref, {"status": "accepted", "respondedAt": t, "connectionId": conn_ref.id})
    # The spark note becomes the first message, so the chat opens with context.
    batch.set(conn_ref.collection("messages").document(), {
        "senderUid": spark["fromUid"], "text": spark["note"], "at": spark["createdAt"],
        "expiresAt": conn["expiresAt"]})
    batch.commit()
    return {"status": "accepted", "connectionId": conn_ref.id}


# ---- Connections (the 24h window) -------------------------------------------------------

def _load_connection(uid: str, conn_id: str) -> tuple[firestore.DocumentReference, dict]:
    ref = db().collection("connections").document(conn_id)
    snap = ref.get()
    if not snap.exists or uid not in snap.get("members"):
        raise HTTPException(404, "Connection not found.")
    conn = snap.to_dict()
    if conn["status"] == "open" and conn["windowEndsAt"] <= now():
        ref.update({"status": "expired"})
        conn["status"] = "expired"
    return ref, conn


def send_message(uid: str, conn_id: str, text: str) -> dict:
    ref, conn = _load_connection(uid, conn_id)
    if conn["status"] not in {"open", "met"}:
        raise HTTPException(409, "This connection's 24-hour window has closed.")
    other = next(m for m in conn["members"] if m != uid)
    if _blocked_pair(uid, other):
        raise HTTPException(409, "This connection is closed.")
    text = (text or "").strip()[:1000]
    if not text:
        raise HTTPException(400, "Message is empty.")
    ok, reason = llm.moderate(text)
    if not ok:
        raise HTTPException(400, reason)
    t = now()
    msg = {"senderUid": uid, "text": text, "at": t}
    if conn.get("expiresAt"):
        msg["expiresAt"] = conn["expiresAt"]
    doc = ref.collection("messages").document()
    doc.set(msg)
    ref.update({"lastMessageAt": t, "lastMessage": text[:80]})
    return {"id": doc.id}


def meetup(uid: str, conn_id: str, action: str, at: str | None = None) -> dict:
    ref, conn = _load_connection(uid, conn_id)
    if conn["status"] != "open":
        raise HTTPException(409, "This connection isn't open.")
    t = now()
    if action == "propose":
        try:
            when = datetime.fromisoformat(at) if at else None
        except ValueError:
            raise HTTPException(400, "Invalid meetup time.")
        if not when or when.tzinfo is None:
            raise HTTPException(400, "Include a timezone-aware meetup time.")
        if not t - timedelta(minutes=5) <= when <= conn["windowEndsAt"]:
            raise HTTPException(400, "Pick a time within your 24-hour window.")
        m = {"at": when, "proposedBy": uid, "confirmedBy": [uid], "proposedAt": t}
        ref.update({"meetup": m})
        return {"meetup": {**m, "at": when.isoformat(), "proposedAt": t.isoformat()}}
    if action in {"accept", "met"}:
        m = conn.get("meetup")
        if not m:
            raise HTTPException(400, "Nobody has proposed a meetup yet.")
        confirmed = sorted(set(m.get("confirmedBy", [])) | {uid})
        upd = {"meetup.confirmedBy": confirmed}
        if action == "met":
            met_by = sorted(set(conn.get("metBy", [])) | {uid})
            upd["metBy"] = met_by
            if set(met_by) == set(conn["members"]):
                # Both confirmed they met: keep the connection and its chat for good.
                upd.update({"status": "met", "metAt": t, "expiresAt": firestore.DELETE_FIELD})
                for s in ref.collection("messages").stream():
                    s.reference.update({"expiresAt": firestore.DELETE_FIELD})
        ref.update(upd)
        return {"ok": True}
    raise HTTPException(400, "Unknown meetup action.")


def close(uid: str, conn_id: str) -> None:
    ref, conn = _load_connection(uid, conn_id)
    if conn["status"] == "open":
        ref.update({"status": "closed", "closedBy": uid})


def block(uid: str, other: str, reason: str = "") -> None:
    db().collection("blocks").document(uid).collection("blocked").document(other).set(
        {"uid": other, "at": now()})
    # Close anything open between the two of them.
    for s in db().collection("connections").where(
            filter=firestore.FieldFilter("members", "array_contains", uid)).stream():
        c = s.to_dict()
        if other in c["members"] and c["status"] == "open":
            s.reference.update({"status": "closed", "closedBy": uid})
    for s in db().collection("sparks").where(filter=firestore.FieldFilter("fromUid", "in", [uid, other])).stream():
        sp = s.to_dict()
        if {sp["fromUid"], sp["toUid"]} == {uid, other} and sp["status"] == "pending":
            s.reference.update({"status": "declined"})
    if reason:
        report(uid, other, reason, None)


def report(uid: str, other: str, reason: str, context: str | None) -> None:
    db().collection("reports").add({"reporterUid": uid, "reportedUid": other,
                                    "reason": (reason or "")[:500], "context": context, "at": now()})


def sweep() -> dict:
    """Flip statuses the TTL will later delete: pending sparks and open windows past due."""
    t = now()
    n_sparks = n_conns = 0
    for s in db().collection("sparks").where(filter=firestore.FieldFilter("status", "==", "pending")) \
            .where(filter=firestore.FieldFilter("expiresAt", "<=", t)).stream():
        s.reference.update({"status": "expired"})
        n_sparks += 1
    for s in db().collection("connections").where(filter=firestore.FieldFilter("status", "==", "open")) \
            .where(filter=firestore.FieldFilter("windowEndsAt", "<=", t)).stream():
        s.reference.update({"status": "expired"})
        n_conns += 1
    return {"sparksExpired": n_sparks, "connectionsExpired": n_conns}
