"""Employee routes: barista board, menu availability, shift size, QR, staff invites."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import auth as firebase_auth
from google.cloud import firestore
from pydantic import BaseModel, EmailStr, Field

from app.auth import require_manager, require_staff, set_role
from app.db import db, now, serialize
from app.routers.customer import _order_out
from app.services import connect, eta, floor, guests, peak
from app.services import menu as menu_svc
from app.services import orders as orders_svc

router = APIRouter(prefix="/staff")


@router.get("/cafes/{cafe_id}/queue")
def queue(cafe_id: str, user: dict = Depends(require_staff)):
    """Initial board state. The UI then keeps it live with a Firestore listener."""
    snaps = (db().collection("orders")
             .where(filter=firestore.FieldFilter("cafeId", "==", cafe_id))
             .where(filter=firestore.FieldFilter("status", "in", ["scheduled", "placed", "in_progress", "ready"]))
             .stream())
    return [_order_out(s.id, s.to_dict()) for s in snaps]


class StatusIn(BaseModel):
    status: str


@router.post("/orders/{order_id}/status")
def set_status(order_id: str, body: StatusIn, user: dict = Depends(require_staff)):
    return orders_svc.set_status(order_id, body.status, user["uid"])


class CafeSettings(BaseModel):
    baristasOnShift: int | None = Field(None, ge=1, le=10)
    connectEnabled: bool | None = None


@router.patch("/cafes/{cafe_id}")
def update_cafe(cafe_id: str, body: CafeSettings, user: dict = Depends(require_staff)):
    upd = body.model_dump(exclude_none=True)
    if "connectEnabled" in upd and user["role"] != "manager":
        raise HTTPException(403, "Only managers can change Connect.")
    if upd:
        db().collection("cafes").document(cafe_id).update(upd)
        menu_svc.invalidate(cafe_id)
        eta.recompute(cafe_id)
    return {"ok": True, **upd}


class Availability(BaseModel):
    available: bool


@router.patch("/cafes/{cafe_id}/menu/{item_id}")
def item_availability(cafe_id: str, item_id: str, body: Availability,
                            user: dict = Depends(require_staff)):
    ref = db().collection("cafes").document(cafe_id).collection("menu").document(item_id)
    if not ref.get().exists:
        raise HTTPException(404, "Item not found")
    ref.update({"available": body.available})
    menu_svc.invalidate(cafe_id)
    return {"ok": True}


@router.get("/cafes/{cafe_id}/checkin-token")
def checkin_token(cafe_id: str, user: dict = Depends(require_staff)):
    return {"cafeId": cafe_id, "token": connect.today_token(cafe_id)}


@router.get("/cafes/{cafe_id}/today")
def today(cafe_id: str, user: dict = Depends(require_staff)):
    cafe = menu_svc.get_cafe(cafe_id)
    local = now().astimezone(menu_svc.tz(cafe))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    orders = [s.to_dict() for s in db().collection("orders")
              .where(filter=firestore.FieldFilter("cafeId", "==", cafe_id))
              .where(filter=firestore.FieldFilter("createdAt", ">=", start)).stream()]
    done = [o for o in orders if o.get("readyAt") and o.get("placedAt")]
    waits = sorted((o["readyAt"] - o["placedAt"]).total_seconds() for o in done)
    live = db().collection("cafes").document(cafe_id).collection("stats").document("live").get()
    live = live.to_dict() if live.exists else {}
    return {
        "orders": len([o for o in orders if o["status"] != "cancelled"]),
        "cancelled": len([o for o in orders if o["status"] == "cancelled"]),
        "revenue": sum(o["total"] for o in orders if o["status"] not in {"cancelled"}),
        "preorders": len([o for o in orders if o.get("scheduledFor")]),
        "medianWaitSec": round(waits[len(waits) // 2]) if waits else None,
        "etaAbsErrorEwmaSec": live.get("etaAbsErrorEwmaSec"),
        "etaErrorP50Sec": live.get("etaErrorP50Sec"),
    }


# ---- Team (managers) -------------------------------------------------------------------

class InviteIn(BaseModel):
    email: EmailStr
    role: str = "staff"


@router.get("/team")
def team(user: dict = Depends(require_manager)):
    members = [{"uid": s.id, **serialize({k: v for k, v in s.to_dict().items()
                                          if k in {"email", "displayName", "role", "lastSeenAt"}})}
               for s in db().collection("users")
               .where(filter=firestore.FieldFilter("role", "in", ["staff", "manager"])).stream()]
    invites = [{"email": s.id, **serialize(s.to_dict())} for s in db().collection("staffInvites")
               .where(filter=firestore.FieldFilter("status", "==", "pending")).stream()]
    return {"members": members, "invites": invites}


@router.post("/team/invites")
def invite(body: InviteIn, user: dict = Depends(require_manager)):
    if body.role not in {"staff", "manager"}:
        raise HTTPException(400, "Role must be staff or manager.")
    email = body.email.lower()
    # Existing account: grant immediately. Otherwise the grant happens on first sign-in.
    try:
        existing = firebase_auth.get_user_by_email(email)
    except firebase_auth.UserNotFoundError:
        existing = None
    if existing:
        set_role(existing.uid, body.role)
        db().collection("users").document(existing.uid).set(
            {"role": body.role, "email": email, "roleRevoked": False}, merge=True)
        return {"status": "granted", "email": email}
    db().collection("staffInvites").document(email).set(
        {"role": body.role, "status": "pending", "invitedBy": user["uid"], "at": now()})
    return {"status": "invited", "email": email}


@router.delete("/team/{uid}")
def remove_member(uid: str, user: dict = Depends(require_manager)):
    if uid == user["uid"]:
        raise HTTPException(400, "You can't remove yourself.")
    set_role(uid, "customer")
    db().collection("users").document(uid).set({"role": "customer", "roleRevoked": True}, merge=True)
    return {"ok": True}


# ---- Floor: tables, waitlist, servers ---------------------------------------------------

@router.get("/cafes/{cafe_id}/floor")
def floor_state(cafe_id: str, user: dict = Depends(require_staff)):
    """Tables, waitlist and on-shift servers. The UI keeps these live via listeners."""
    return {
        "tables": [serialize(t) for t in floor.tables(cafe_id)],
        "waitlist": [serialize(p) for p in floor.waitlist(cafe_id)],
        "servers": [serialize(s) for s in floor.servers(cafe_id)],
        "suggestions": floor.suggestions(cafe_id),
        "stats": floor.floor_stats(cafe_id),
    }


class SeatIn(BaseModel):
    partyId: str | None = None
    size: int | None = Field(None, ge=1, le=12)
    serverUid: str | None = None


@router.post("/cafes/{cafe_id}/tables/{table_id}/seat")
def seat(cafe_id: str, table_id: str, body: SeatIn, user: dict = Depends(require_staff)):
    return floor.seat(cafe_id, table_id, body.partyId, body.size, body.serverUid, user["uid"])


@router.post("/cafes/{cafe_id}/tables/{table_id}/clear")
def clear(cafe_id: str, table_id: str, user: dict = Depends(require_staff)):
    return floor.clear(cafe_id, table_id)


@router.post("/cafes/{cafe_id}/tables/{table_id}/ready")
def table_ready(cafe_id: str, table_id: str, user: dict = Depends(require_staff)):
    return floor.mark_ready(cafe_id, table_id)


class WalkInIn(BaseModel):
    name: str = "Walk-in"
    size: int = Field(ge=1, le=12)
    seating: str = "any"


@router.post("/cafes/{cafe_id}/waitlist")
def add_walk_in(cafe_id: str, body: WalkInIn, user: dict = Depends(require_staff)):
    return serialize(floor.join(cafe_id, None, body.name, body.size, body.seating, "host"))


@router.delete("/cafes/{cafe_id}/waitlist/{party_id}")
def remove_party(cafe_id: str, party_id: str, user: dict = Depends(require_staff)):
    floor.leave(cafe_id, party_id)
    return {"ok": True}


class ShiftIn(BaseModel):
    onShift: bool


@router.post("/cafes/{cafe_id}/shift")
def shift(cafe_id: str, body: ShiftIn, user: dict = Depends(require_staff)):
    name = (db().collection("users").document(user["uid"]).get().to_dict() or {}).get("displayName") or user["email"]
    return floor.set_shift(cafe_id, user["uid"], name, body.onShift)


@router.get("/cafes/{cafe_id}/table-codes")
def table_codes(cafe_id: str, user: dict = Depends(require_staff)):
    """Today's QR token for every table (they rotate daily)."""
    return [{"id": t["id"], "label": t["label"], "seats": t["seats"], "zone": t["zone"],
             "token": floor.table_token(cafe_id, t["id"])} for t in floor.tables(cafe_id)]


# ---- Peak shaving: forecast, impact, demo ------------------------------------------

@router.get("/cafes/{cafe_id}/forecast")
def forecast(cafe_id: str, date: str | None = None, user: dict = Depends(require_staff)):
    return peak.forecast(cafe_id, date)


@router.get("/cafes/{cafe_id}/impact")
def impact(cafe_id: str, days: int = 7, user: dict = Depends(require_staff)):
    return peak.impact(cafe_id, max(1, min(days, 28)))


@router.post("/cafes/{cafe_id}/demo")
def simulate_demo(cafe_id: str, user: dict = Depends(require_manager)):
    return peak.simulate_demo(cafe_id)


@router.delete("/cafes/{cafe_id}/demo")
def clear_demo(cafe_id: str, user: dict = Depends(require_manager)):
    return peak.clear_demo(cafe_id)


# ---- Guests: profiles, segments, targeted campaigns ---------------------------------

@router.get("/cafes/{cafe_id}/guests")
def list_guests(cafe_id: str, segment: str | None = None, user: dict = Depends(require_staff)):
    return guests.list_guests(cafe_id, segment, manager=user["role"] == "manager")


@router.get("/cafes/{cafe_id}/guests/{uid}")
def guest_detail(cafe_id: str, uid: str, user: dict = Depends(require_staff)):
    return guests.detail(cafe_id, uid, manager=user["role"] == "manager")


class CampaignIn(BaseModel):
    segment: str
    beans: int = 20


@router.post("/cafes/{cafe_id}/campaigns")
def campaign(cafe_id: str, body: CampaignIn, user: dict = Depends(require_staff)):
    return guests.campaign(cafe_id, body.segment, body.beans, user["uid"])
