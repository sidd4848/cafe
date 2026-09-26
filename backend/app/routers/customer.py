"""Guest-facing routes: profile, menu, ordering chat, cart, orders, waits, discovery."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import auth as firebase_auth
from google.cloud import firestore
from pydantic import BaseModel, Field

from app.auth import require_user, set_role
from app.config import BOOTSTRAP_MANAGERS
from app.db import db, now, serialize
from app.menu_data import CATEGORIES, MODIFIERS
from app.services import busyness, cart as cart_svc, eta, llm
from app.services import menu as menu_svc
from app.services import ordering_agent, orders as orders_svc, recommender

logger = logging.getLogger(__name__)
router = APIRouter()


# ---- Me --------------------------------------------------------------------------------

def _user_doc(uid: str) -> dict:
    snap = db().collection("users").document(uid).get()
    return snap.to_dict() if snap.exists else {}


@router.get("/me")
def me(user: dict = Depends(require_user)):
    """
    Ensure the user doc exists and resolve the role. A pending staff invite or a
    bootstrap-manager email upgrades the role claim; `roleChanged` tells the client to
    refresh its ID token so the new claim reaches Firestore rules.
    """
    ref = db().collection("users").document(user["uid"])
    doc = _user_doc(user["uid"])
    role = user["role"]
    new_role = role
    if user["email"] and user["email_verified"]:
        if user["email"] in BOOTSTRAP_MANAGERS:
            new_role = "manager"
        else:
            invite = db().collection("staffInvites").document(user["email"]).get()
            if invite.exists and invite.get("status") == "pending":
                new_role = invite.get("role")
                invite.reference.update({"status": "accepted", "uid": user["uid"], "acceptedAt": now()})
    if doc.get("role") in {"staff", "manager"} and role == "customer" and not doc.get("roleRevoked"):
        new_role = doc["role"]
    if new_role != role:
        set_role(user["uid"], new_role)

    base = {"email": user["email"], "role": new_role, "lastSeenAt": now()}
    if not doc:
        base.update({"displayName": user["name"] or user["email"].split("@")[0], "photoURL": user["picture"],
                     "createdAt": now(), "prefs": {}})
    ref.set(base, merge=True)
    doc = {**doc, **base}
    return {
        "uid": user["uid"], "email": user["email"], "role": new_role, "roleChanged": new_role != role,
        "displayName": doc.get("displayName"), "photoURL": doc.get("photoURL"),
        "prefs": doc.get("prefs") or {}, "onboarded": bool(doc.get("onboardedAt")),
        "usuals": doc.get("usuals") or [],
    }


class Prefs(BaseModel):
    temperature: str | None = None       # hot | iced | any
    sweetness: int | None = Field(None, ge=0, le=3)
    milk: str | None = None              # dairy | oat | almond | soy | none
    caffeine: str | None = None          # none | light | regular | strong
    flavours: list[str] = []
    diet: str = "any"                    # any | veg | vegan
    avoid: list[str] = []                # nuts | gluten | egg | dairy
    dislikes: list[str] = []
    displayName: str | None = None


@router.put("/me/prefs")
def put_prefs(body: Prefs, user: dict = Depends(require_user)):
    prefs = body.model_dump(exclude={"displayName"})
    upd = {"prefs": prefs, "onboardedAt": now()}
    if body.displayName:
        upd["displayName"] = body.displayName.strip()[:40]
    try:
        upd["prefsEmbedding"] = llm.embed(recommender.prefs_text(prefs), task="RETRIEVAL_QUERY")
    except Exception as e:
        logger.warning(f"Could not embed preferences: {e}")
    db().collection("users").document(user["uid"]).set(upd, merge=True)
    return {"prefs": prefs}


def _set_pref(uid: str, key: str, value: str) -> None:
    ref = db().collection("users").document(uid)
    prefs = dict((_user_doc(uid).get("prefs") or {}))
    if key == "avoid":
        prefs["avoid"] = sorted(set(prefs.get("avoid", [])) | {value.lower()})
    elif key == "sweetness":
        try:
            prefs[key] = max(0, min(3, int(value)))
        except ValueError:
            prefs[key] = {"none": 0, "less": 1, "regular": 2, "sweet": 3}.get(value.lower(), 2)
    else:
        prefs[key] = value.lower()
    upd = {"prefs": prefs}
    try:
        upd["prefsEmbedding"] = llm.embed(recommender.prefs_text(prefs), task="RETRIEVAL_QUERY")
    except Exception:
        pass
    ref.set(upd, merge=True)


# ---- Cafes & menu ----------------------------------------------------------------------

@router.get("/cafes")
def cafes(user: dict = Depends(require_user)):
    out = []
    for s in db().collection("cafes").stream():
        c = s.to_dict()
        out.append({"id": s.id, "name": c["name"], "address": c.get("address"),
                    "open": c.get("open"), "close": c.get("close"),
                    "isOpen": menu_svc.is_open(c, now())})
    return out


@router.get("/cafes/{cafe_id}")
def cafe(cafe_id: str, user: dict = Depends(require_user)):
    c = menu_svc.get_cafe(cafe_id)
    return {"id": cafe_id, "name": c["name"], "address": c.get("address"), "open": c.get("open"),
            "close": c.get("close"), "timezone": c.get("timezone"), "isOpen": menu_svc.is_open(c, now()),
            "connectEnabled": c.get("connectEnabled", False), "baristasOnShift": c.get("baristasOnShift")}


@router.get("/cafes/{cafe_id}/menu")
def menu(cafe_id: str, user: dict = Depends(require_user)):
    items = menu_svc.get_menu(cafe_id).values()
    staff = user["role"] in {"staff", "manager"}
    return {
        "categories": CATEGORIES,
        "modifiers": MODIFIERS,
        "items": [menu_svc.public_item(i) for i in sorted(items, key=lambda i: i["price"])
                  if staff or i.get("available", True)],
    }


# ---- Ordering session (chat + cart) ---------------------------------------------------

def _session_ref(uid: str, cafe_id: str):
    return db().collection("orderSessions").document(f"{uid}_{cafe_id}")


def _session_out(s: dict) -> dict:
    return {"cafeId": s["cafeId"], "messages": s.get("messages", []), "cart": s.get("cart", []),
            "total": cart_svc.total(s.get("cart", [])),
            "pickupAt": s["pickupAt"].isoformat() if isinstance(s.get("pickupAt"), datetime) else None}


def _load_session(uid: str, cafe_id: str) -> dict:
    snap = _session_ref(uid, cafe_id).get()
    s = snap.to_dict() if snap.exists else None
    if not s or s.get("expiresAt", now()) <= now():
        s = {"uid": uid, "cafeId": cafe_id, "messages": [], "cart": [], "pickupAt": None}
    if isinstance(s.get("pickupAt"), datetime) and s["pickupAt"] < now():
        s["pickupAt"] = None
    for m in s.get("messages", []):
        if isinstance(m.get("at"), datetime):
            m["at"] = m["at"].isoformat()
    return s


def _save_session(uid: str, cafe_id: str, s: dict) -> None:
    from datetime import timedelta
    _session_ref(uid, cafe_id).set({**s, "uid": uid, "cafeId": cafe_id,
                                    "updatedAt": now(), "expiresAt": now() + timedelta(hours=6)})


@router.get("/cafes/{cafe_id}/session")
def get_session(cafe_id: str, user: dict = Depends(require_user)):
    return _session_out(_load_session(user["uid"], cafe_id))


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


_chat_log: dict[str, list[float]] = {}


@router.post("/cafes/{cafe_id}/session/chat")
def chat(cafe_id: str, body: ChatIn, user: dict = Depends(require_user)):
    import time
    window = [t for t in _chat_log.get(user["uid"], []) if time.time() - t < 3600]
    if len(window) >= 60:
        raise HTTPException(429, "That's a lot of chatting! Try again in a bit.")
    _chat_log[user["uid"]] = window + [time.time()]

    s = _load_session(user["uid"], cafe_id)
    try:
        s["cart"] = cart_svc.reprice(s.get("cart", []), menu_svc.get_menu(cafe_id))
    except cart_svc.CartError:
        s["cart"] = []
    udoc = {**_user_doc(user["uid"]), "uid": user["uid"]}
    try:
        result = ordering_agent.run_turn(cafe_id, user["uid"], udoc, s, body.text,
                                         on_pref=lambda k, v: _set_pref(user["uid"], k, v))
    except Exception as e:
        logger.exception(f"Ordering agent failed: {e}")
        raise HTTPException(502, "The barista assistant is unavailable. You can still order from the menu.")
    t = now().isoformat()
    s["messages"] = (s.get("messages", []) + [{"role": "user", "text": body.text, "at": t},
                                              {"role": "assistant", "text": result["reply"], "at": t,
                                               "actions": result["actions"]}])[-40:]
    s["cart"], s["pickupAt"] = result["cart"], result["pickupAt"]
    _save_session(user["uid"], cafe_id, s)
    return _session_out(s)


class CartOp(BaseModel):
    op: str
    itemId: str | None = None
    lineId: str | None = None
    qty: int | None = None
    modifiers: dict | None = None


@router.post("/cafes/{cafe_id}/session/cart")
def cart_op(cafe_id: str, body: CartOp, user: dict = Depends(require_user)):
    s = _load_session(user["uid"], cafe_id)
    op = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        s["cart"] = cart_svc.apply_op(s.get("cart", []), menu_svc.get_menu(cafe_id), op)
    except cart_svc.CartError as e:
        raise HTTPException(400, str(e))
    _save_session(user["uid"], cafe_id, s)
    return _session_out(s)


class PickupIn(BaseModel):
    pickupAt: datetime | None = None


@router.put("/cafes/{cafe_id}/session/pickup")
def set_pickup(cafe_id: str, body: PickupIn, user: dict = Depends(require_user)):
    s = _load_session(user["uid"], cafe_id)
    s["pickupAt"] = body.pickupAt
    _save_session(user["uid"], cafe_id, s)
    return _session_out(s)


@router.delete("/cafes/{cafe_id}/session")
def reset_session(cafe_id: str, user: dict = Depends(require_user)):
    _session_ref(user["uid"], cafe_id).delete()
    return {"ok": True}


# ---- Orders ----------------------------------------------------------------------------

class CheckoutIn(BaseModel):
    paymentMethod: str
    pickupAt: datetime | None = None
    notes: str = ""
    tableId: str | None = None      # dine-in: order to this table (from its QR)
    tableToken: str | None = None


def _order_out(oid: str, o: dict) -> dict:
    out = serialize(o)
    out["id"] = oid
    if isinstance(o.get("eta"), dict):
        out["eta"] = serialize(o["eta"])
    if isinstance(o.get("payment"), dict):
        out["payment"] = serialize(o["payment"])
    return out


@router.post("/cafes/{cafe_id}/checkout")
def checkout(cafe_id: str, body: CheckoutIn, user: dict = Depends(require_user)):
    s = _load_session(user["uid"], cafe_id)
    udoc = _user_doc(user["uid"])
    source = "chat" if any(m["role"] == "user" for m in s.get("messages", [])) else "menu"
    table = None
    if body.tableId:
        from app.services import floor
        table = floor.verify_table(cafe_id, body.tableId, body.tableToken or "")
    order = orders_svc.create(user["uid"], {**udoc, "email": user["email"]}, cafe_id, s.get("cart", []),
                              body.paymentMethod, None if table else (body.pickupAt or s.get("pickupAt")),
                              source, body.notes, table)
    _session_ref(user["uid"], cafe_id).delete()
    oid = order.pop("id")
    return _order_out(oid, order)


@router.get("/orders")
def my_orders(user: dict = Depends(require_user)):
    snaps = (db().collection("orders").where(filter=firestore.FieldFilter("uid", "==", user["uid"]))
             .order_by("createdAt", direction=firestore.Query.DESCENDING).limit(30).stream())
    return [_order_out(s.id, s.to_dict()) for s in snaps]


@router.get("/orders/{order_id}")
def get_order(order_id: str, user: dict = Depends(require_user)):
    _, o = orders_svc.get_owned(user["uid"], order_id, staff=user["role"] in {"staff", "manager"})
    return _order_out(order_id, o)


@router.post("/orders/{order_id}/cancel")
def cancel(order_id: str, user: dict = Depends(require_user)):
    return orders_svc.cancel_by_guest(user["uid"], order_id)


@router.post("/orders/{order_id}/reorder")
def reorder(order_id: str, user: dict = Depends(require_user)):
    _, o = orders_svc.get_owned(user["uid"], order_id)
    s = _load_session(user["uid"], o["cafeId"])
    menu_items = menu_svc.get_menu(o["cafeId"])
    skipped = []
    for l in o["items"]:
        try:
            s["cart"] = cart_svc.apply_op(s.get("cart", []), menu_items,
                                          {"op": "add", "itemId": l["itemId"], "qty": l["qty"],
                                           "modifiers": l["modifiers"]})
        except cart_svc.CartError:
            skipped.append(l["name"])
    _save_session(user["uid"], o["cafeId"], s)
    return {**_session_out(s), "skipped": skipped}


# ---- Waits -----------------------------------------------------------------------------

@router.get("/cafes/{cafe_id}/wait")
def wait(cafe_id: str, user: dict = Depends(require_user)):
    snap = db().collection("cafes").document(cafe_id).collection("stats").document("live").get()
    live = snap.to_dict() if snap.exists else None
    if not live or (now() - live["updatedAt"]).total_seconds() > 120:
        live = eta.recompute(cafe_id)
    return serialize({k: v for k, v in live.items() if k != "recentErrorsSec"})


@router.get("/cafes/{cafe_id}/best-times")
def best_times(cafe_id: str, date: str | None = None, user: dict = Depends(require_user)):
    return busyness.best_times(cafe_id, date)


class PlanIn(BaseModel):
    minutesAway: int = Field(ge=0, le=240)


@router.post("/cafes/{cafe_id}/plan-arrival")
def plan_arrival(cafe_id: str, body: PlanIn, user: dict = Depends(require_user)):
    """Given the cart and travel time: order now, or pre-order timed for arrival."""
    from datetime import timedelta
    s = _load_session(user["uid"], cafe_id)
    order_like = {"items": s.get("cart") or [{"itemId": "cafe_latte", "qty": 1}]}
    ready_if_now = eta.earliest_ready(cafe_id, order_like)
    arrival = now() + timedelta(minutes=body.minutesAway)
    if ready_if_now >= arrival:
        advice = "Order now: it'll take about as long to make as it takes you to get here."
        pickup = None
    else:
        advice = "We'll hold your order and start it so it's fresh when you walk in."
        pickup = arrival
    return {"arrivalAt": arrival.isoformat(), "readyIfOrderedNow": ready_if_now.isoformat(),
            "suggestedPickupAt": pickup.isoformat() if pickup else None, "advice": advice}


# ---- Discovery -------------------------------------------------------------------------

@router.get("/cafes/{cafe_id}/recommendations")
def recommendations(cafe_id: str, n: int = 6, user: dict = Depends(require_user)):
    s = _load_session(user["uid"], cafe_id)
    udoc = _user_doc(user["uid"])
    return recommender.recommend(cafe_id, user["uid"], udoc, n=min(max(n, 1), 12),
                                 cart_item_ids=[l["itemId"] for l in s.get("cart", [])])


class InteractionIn(BaseModel):
    itemId: str
    type: str


@router.post("/interactions")
def interaction(body: InteractionIn, user: dict = Depends(require_user)):
    if body.type not in {"like", "dismiss", "view"}:
        raise HTTPException(400, "Unknown interaction")
    db().collection("users").document(user["uid"]).collection("interactions").add(
        {"itemId": body.itemId, "type": body.type, "at": now()})

    return {"ok": True}
