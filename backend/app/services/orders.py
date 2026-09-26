"""
Orders: placement (with fake payment and pre-ordering), status changes, cancellation.

Status flow:
    scheduled --(eta engine releases it)--> placed -> in_progress -> ready -> collected
    scheduled | placed --> cancelled (by the guest); any active state --> cancelled (staff)

Payment is simulated: "upi" and "card" succeed instantly with a DEMO- transaction id,
"counter" leaves the order unpaid until staff mark it collected. No card or UPI details
are ever collected.
"""

import secrets
import string
from datetime import datetime, timedelta

from fastapi import HTTPException
from google.cloud import firestore

from app.db import db, now
from app.services import cart as cart_svc
from app.services import eta
from app.services import loyalty
from app.services import menu as menu_svc

PAYMENT_METHODS = {"upi", "card", "counter"}
MAX_PREORDER_DAYS = 7
MIN_PREORDER_LEAD = timedelta(minutes=5)

TRANSITIONS = {
    "placed": {"in_progress", "cancelled"},
    "in_progress": {"ready", "cancelled"},
    "ready": {"collected"},
    "scheduled": {"cancelled", "placed"},
}


def _pickup_code() -> str:
    alphabet = "ACDEFHJKMNPRTUVWXY34679"
    return "".join(secrets.choice(alphabet) for _ in range(3))


def create(uid: str, user: dict, cafe_id: str, lines: list[dict], payment_method: str,
           scheduled_for: datetime | None, source: str, notes: str = "",
           table: dict | None = None) -> dict:
    cafe = menu_svc.get_cafe(cafe_id)
    menu = menu_svc.get_menu(cafe_id)
    if not lines:
        raise HTTPException(400, "Your cart is empty.")
    try:
        items = cart_svc.reprice(lines, menu)
    except cart_svc.CartError as e:
        raise HTTPException(409, str(e))
    if payment_method not in PAYMENT_METHODS:
        raise HTTPException(400, "Choose UPI, card or pay at counter.")

    t = now()
    status = "placed"
    if scheduled_for:
        if scheduled_for.tzinfo is None:
            raise HTTPException(400, "Pickup time needs a timezone.")
        if scheduled_for > t + timedelta(days=MAX_PREORDER_DAYS):
            raise HTTPException(400, f"Pre-orders can be up to {MAX_PREORDER_DAYS} days ahead.")
        if not menu_svc.is_open(cafe, scheduled_for):
            raise HTTPException(400, f"We're open {cafe.get('open')}-{cafe.get('close')}; pick a time then.")
        # A pickup time sooner than the queue can manage is just an ASAP order.
        if scheduled_for > max(t + MIN_PREORDER_LEAD, eta.earliest_ready(cafe_id, {"items": items})):
            status = "scheduled"
        else:
            scheduled_for = None
    elif not menu_svc.is_open(cafe, t):
        raise HTTPException(400, "We're closed right now. Pre-order for when we open.")

    paid = payment_method in {"upi", "card"}
    order = {
        "uid": uid,
        "customerName": (user.get("displayName") or user.get("email") or "Guest").split(" ")[0],
        "cafeId": cafe_id,
        "items": [{**l, "prepSec": round(eta.item_prep(menu, l["itemId"])[0])} for l in items],
        "total": cart_svc.total(items),
        "notes": (notes or "")[:200],
        "status": status,
        "pickupCode": _pickup_code(),
        "source": source,
        "dineIn": bool(table),
        "tableId": table["id"] if table else None,
        "tableLabel": table["label"] if table else None,
        "createdAt": t,
        "placedAt": t if status == "placed" else None,
        "scheduledFor": scheduled_for,
        "payment": {
            "method": payment_method,
            "status": "paid" if paid else "pending",
            "txnId": f"DEMO-{secrets.token_hex(5).upper()}" if paid else None,
            "paidAt": t if paid else None,
        },
    }
    ref = db().collection("orders").document()
    ref.set(order)
    eta.recompute(cafe_id)
    _record_interactions(uid, items, t)
    _update_usuals(uid, items)
    loyalty.record_order(uid, order["total"], t.astimezone(menu_svc.tz(cafe)).date().isoformat())
    return {"id": ref.id, **ref.get().to_dict()}


def _record_interactions(uid: str, items: list[dict], t: datetime) -> None:
    batch = db().batch()
    col = db().collection("users").document(uid).collection("interactions")
    for l in items:
        batch.set(col.document(), {"itemId": l["itemId"], "type": "order", "at": t})
    batch.commit()


def _update_usuals(uid: str, items: list[dict]) -> None:
    ref = db().collection("users").document(uid)
    snap = ref.get()
    usuals = list((snap.to_dict() or {}).get("usuals", [])) if snap.exists else []
    for l in items:
        key = (l["itemId"], tuple(sorted(l["modifiers"].items())))
        for u in usuals:
            if (u["itemId"], tuple(sorted(u["modifiers"].items()))) == key:
                u["count"] += l["qty"]
                break
        else:
            usuals.append({"itemId": l["itemId"], "name": l["name"], "modifiers": l["modifiers"],
                           "modifierLabels": l["modifierLabels"], "count": l["qty"]})
    usuals.sort(key=lambda u: u["count"], reverse=True)
    ref.set({"usuals": usuals[:5]}, merge=True)


def get_owned(uid: str, order_id: str, staff: bool = False) -> tuple[firestore.DocumentReference, dict]:
    ref = db().collection("orders").document(order_id)
    snap = ref.get()
    if not snap.exists or (not staff and snap.get("uid") != uid):
        raise HTTPException(404, "Order not found.")
    return ref, snap.to_dict()


def set_status(order_id: str, new_status: str, staff_uid: str) -> dict:
    ref, order = get_owned("", order_id, staff=True)
    if new_status not in TRANSITIONS.get(order["status"], set()):
        raise HTTPException(409, f"Can't move an order from {order['status']} to {new_status}.")
    t = now()
    upd: dict = {"status": new_status, "updatedBy": staff_uid}
    if new_status == "placed":
        upd["placedAt"] = t
    elif new_status == "in_progress":
        upd["startedAt"] = t
    elif new_status == "ready":
        upd["readyAt"] = t
    elif new_status == "collected":
        upd["collectedAt"] = t
        if order["payment"]["status"] == "pending":
            upd["payment.status"] = "paid"
            upd["payment.paidAt"] = t
            upd["payment.txnId"] = f"DEMO-COUNTER-{secrets.token_hex(3).upper()}"
    elif new_status == "cancelled":
        upd["cancelledAt"] = t
        if order["payment"]["status"] == "paid":
            upd["payment.status"] = "refunded"
        loyalty.refund(order["uid"], order["total"])
    ref.update(upd)
    if new_status == "ready":
        eta.learn_from_completion(order["cafeId"], order, t)
    eta.recompute(order["cafeId"])
    return {"id": order_id, "status": new_status}


def cancel_by_guest(uid: str, order_id: str) -> dict:
    ref, order = get_owned(uid, order_id)
    if order["status"] not in {"placed", "scheduled"}:
        raise HTTPException(409, "The barista has already started this order.")
    t = now()
    upd = {"status": "cancelled", "cancelledAt": t}
    if order["payment"]["status"] == "paid":
        upd["payment.status"] = "refunded"
    ref.update(upd)
    loyalty.refund(uid, order["total"])
    eta.recompute(order["cafeId"])
    return {"id": order_id, "status": "cancelled"}


def pay_open_orders(uid: str, cafe_id: str, table_id: str, method: str) -> dict:
    """Tableside checkout: settle this guest's unpaid orders at this table (simulated)."""
    if method not in {"upi", "card"}:
        raise HTTPException(400, "Choose UPI or card.")
    t = now()
    paid, total = [], 0
    for s in (db().collection("orders").where(filter=firestore.FieldFilter("uid", "==", uid))
              .where(filter=firestore.FieldFilter("tableId", "==", table_id)).stream()):
        o = s.to_dict()
        if o["cafeId"] != cafe_id or o["status"] == "cancelled" or o["payment"]["status"] != "pending":
            continue
        s.reference.update({"payment.status": "paid", "payment.method": method, "payment.paidAt": t,
                            "payment.txnId": f"DEMO-TABLE-{secrets.token_hex(3).upper()}"})
        paid.append(s.id)
        total += o["total"]
    return {"paidOrders": paid, "total": total}
