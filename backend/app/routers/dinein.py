"""Guest routes for loyalty/context, the dietary filter, the dine-in waitlist and tables."""

from fastapi import APIRouter, Depends
from google.cloud import firestore
from pydantic import BaseModel, Field

from app.auth import require_user
from app.db import db, serialize
from app.routers.customer import _order_out, _user_doc
from app.services import context as context_svc
from app.services import floor, loyalty, menu_filter, peak
from app.services import menu as menu_svc
from app.services import orders as orders_svc

router = APIRouter()


@router.get("/cafes/{cafe_id}/welcome")
def welcome(cafe_id: str, user: dict = Depends(require_user)):
    """Loyalty profile + weather/time context, for the home screen and on check-in."""
    u = _user_doc(user["uid"])
    ctx = context_svc.snapshot(cafe_id)
    return {"greeting": u.get("displayName"), "loyalty": loyalty.summary(u), "context": ctx}


class FilterIn(BaseModel):
    query: str = Field(min_length=2, max_length=200)


@router.post("/cafes/{cafe_id}/menu/filter")
def filter_menu(cafe_id: str, body: FilterIn, user: dict = Depends(require_user)):
    f = menu_filter.parse(body.query)
    items = [i for i in menu_svc.get_menu(cafe_id).values() if i.get("available", True)]
    keep, excluded = menu_filter.apply(items, f)
    return {"summary": f.get("summary") or body.query, "filter": f, "itemIds": keep, "excluded": excluded}


# ---- Waitlist -------------------------------------------------------------------------

@router.get("/cafes/{cafe_id}/table-wait")
def table_wait(cafe_id: str, party: int = 2, seating: str = "any", user: dict = Depends(require_user)):
    return floor.quote(cafe_id, max(1, min(party, 12)), seating)


class JoinIn(BaseModel):
    size: int = Field(ge=1, le=12)
    seating: str = "any"  # any | bar | no_bar
    name: str = ""


@router.post("/cafes/{cafe_id}/waitlist")
def join_waitlist(cafe_id: str, body: JoinIn, user: dict = Depends(require_user)):
    name = body.name or _user_doc(user["uid"]).get("displayName") or "Guest"
    return serialize(floor.join(cafe_id, user["uid"], name, body.size, body.seating, "app"))


@router.get("/cafes/{cafe_id}/waitlist/me")
def my_waitlist(cafe_id: str, user: dict = Depends(require_user)):
    e = floor.my_entry(cafe_id, user["uid"])
    return serialize(e) if e else None


@router.delete("/cafes/{cafe_id}/waitlist/{party_id}")
def leave_waitlist(cafe_id: str, party_id: str, user: dict = Depends(require_user)):
    floor.leave(cafe_id, party_id, user["uid"])
    return {"ok": True}


# ---- Table QR landing & tableside checkout -------------------------------------------

@router.get("/cafes/{cafe_id}/tables/{table_id}")
def table_landing(cafe_id: str, table_id: str, t: str, user: dict = Depends(require_user)):
    tb = floor.verify_table(cafe_id, table_id, t)
    mine = [
        _order_out(s.id, s.to_dict()) for s in db().collection("orders")
        .where(filter=firestore.FieldFilter("uid", "==", user["uid"]))
        .where(filter=firestore.FieldFilter("tableId", "==", table_id)).stream()
        if s.to_dict()["status"] != "cancelled"
    ]
    open_orders = [o for o in mine if o["payment"]["status"] == "pending"]
    return {"table": {"id": tb["id"], "label": tb["label"], "seats": tb["seats"], "zone": tb["zone"],
                      "serverName": tb.get("serverName")},
            "openOrders": open_orders, "balance": sum(o["total"] for o in open_orders),
            "cafe": {"id": cafe_id, "name": menu_svc.get_cafe(cafe_id)["name"]}}


class PayIn(BaseModel):
    t: str
    method: str


@router.post("/cafes/{cafe_id}/tables/{table_id}/pay")
def pay_table(cafe_id: str, table_id: str, body: PayIn, user: dict = Depends(require_user)):
    floor.verify_table(cafe_id, table_id, body.t)
    return orders_svc.pay_open_orders(user["uid"], cafe_id, table_id, body.method)


# ---- Peak shaving: offers ----------------------------------------------------------

def _nudge_out(n: dict | None) -> dict | None:
    if not n:
        return None
    return {"id": n["id"], "fromAt": n["fromAt"].isoformat(), "toAt": n["toAt"].isoformat(),
            "fromWaitSec": n.get("fromWaitSec"), "toWaitSec": n.get("toWaitSec"),
            "beans": n["beans"], "status": n["status"]}


@router.get("/cafes/{cafe_id}/nudge")
def get_nudge(cafe_id: str, context: str = "home", user: dict = Depends(require_user)):
    """A personal offer to shift out of an upcoming rush, or null."""
    if context not in {"home", "checkout"}:
        context = "home"
    return _nudge_out(peak.offer(cafe_id, user["uid"], _user_doc(user["uid"]), context))


class NudgeResponse(BaseModel):
    accept: bool


@router.post("/nudges/{nudge_id}/respond")
def respond_nudge(nudge_id: str, body: NudgeResponse, user: dict = Depends(require_user)):
    return peak.respond(user["uid"], nudge_id, body.accept)
