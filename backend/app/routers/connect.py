"""Connect routes. Realtime reads (sparks, connections, messages) use Firestore listeners."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import require_user
from app.services import connect

router = APIRouter(prefix="/connect")


@router.get("/options")
def options(user: dict = Depends(require_user)):
    return {"interests": connect.INTERESTS, "openTo": connect.OPEN_TO}


@router.get("/profile")
def get_profile(user: dict = Depends(require_user)):
    p = connect.get_profile(user["uid"]) or {}
    p.pop("updatedAt", None)
    return {"profile": p or None, "presence": connect.status(user["uid"])}


class ProfileIn(BaseModel):
    firstName: str = Field(max_length=40)
    bio: str = Field("", max_length=140)
    interests: list[str] = []
    openTo: list[str] = []
    visible: bool = False
    ageConfirmed18: bool = False


@router.put("/profile")
def put_profile(body: ProfileIn, user: dict = Depends(require_user)):
    p = connect.upsert_profile(user["uid"], body.model_dump())
    p.pop("updatedAt", None)
    return p


class CheckinIn(BaseModel):
    cafeId: str
    token: str
    mood: str = ""
    tableId: str | None = None


@router.post("/checkin")
def checkin(body: CheckinIn, user: dict = Depends(require_user)):
    return connect.check_in(user["uid"], body.cafeId, body.token, body.mood, body.tableId)


class CafeIn(BaseModel):
    cafeId: str


@router.post("/checkout")
def checkout(body: CafeIn, user: dict = Depends(require_user)):
    connect.check_out(user["uid"], body.cafeId)
    return {"ok": True}


@router.get("/cafes/{cafe_id}/people")
def people(cafe_id: str, user: dict = Depends(require_user)):
    return connect.people_here(user["uid"], cafe_id)


@router.get("/sparks/draft")
def draft(toUid: str, cafeId: str, user: dict = Depends(require_user)):
    return connect.draft_spark(user["uid"], toUid, cafeId)


class SparkIn(BaseModel):
    toUid: str
    cafeId: str
    note: str = Field(max_length=280)


@router.post("/sparks")
def spark(body: SparkIn, user: dict = Depends(require_user)):
    return connect.send_spark(user["uid"], body.toUid, body.cafeId, body.note)


@router.post("/sparks/{spark_id}/accept")
def accept(spark_id: str, user: dict = Depends(require_user)):
    return connect.respond_spark(user["uid"], spark_id, True)


@router.post("/sparks/{spark_id}/decline")
def decline(spark_id: str, user: dict = Depends(require_user)):
    return connect.respond_spark(user["uid"], spark_id, False)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@router.post("/connections/{conn_id}/messages")
def message(conn_id: str, body: MessageIn, user: dict = Depends(require_user)):
    return connect.send_message(user["uid"], conn_id, body.text)


class MeetupIn(BaseModel):
    action: str  # propose | accept | met
    at: str | None = None


@router.post("/connections/{conn_id}/meetup")
def meetup(conn_id: str, body: MeetupIn, user: dict = Depends(require_user)):
    return connect.meetup(user["uid"], conn_id, body.action, body.at)


@router.post("/connections/{conn_id}/close")
def close(conn_id: str, user: dict = Depends(require_user)):
    connect.close(user["uid"], conn_id)
    return {"ok": True}


class BlockIn(BaseModel):
    uid: str
    reason: str = ""
    context: str | None = None


@router.post("/block")
def block(body: BlockIn, user: dict = Depends(require_user)):
    connect.block(user["uid"], body.uid, body.reason)
    return {"ok": True}


@router.post("/report")
def report(body: BlockIn, user: dict = Depends(require_user)):
    connect.report(user["uid"], body.uid, body.reason, body.context)
    return {"ok": True}
