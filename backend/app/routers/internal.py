"""Cloud Scheduler jobs. Only a Google OIDC token for the scheduler SA gets in."""

import logging

from fastapi import APIRouter, Depends

from app.auth import require_scheduler
from app.db import db
from app.services import busyness, connect, eta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/jobs", dependencies=[Depends(require_scheduler)])


@router.post("/sweep")
def sweep():
    """Every minute: release due pre-orders, refresh ETAs, expire sparks and windows."""
    results = {}
    for s in db().collection("cafes").stream():
        try:
            results[s.id] = eta.recompute(s.id)["activeOrders"]
        except Exception as e:
            logger.exception(f"Recompute failed for {s.id}: {e}")
    return {"activeOrders": results, **connect.sweep()}


@router.post("/busyness")
def rebuild_busyness():
    """Nightly: fold real orders into the busyness profile and refresh popularity."""
    from datetime import timedelta

    from google.cloud import firestore

    from app.db import now
    from app.services import menu as menu_svc

    out = {}
    for s in db().collection("cafes").stream():
        out[s.id] = busyness.rebuild(s.id)
        counts: dict[str, int] = {}
        for o in (db().collection("orders").where(filter=firestore.FieldFilter("cafeId", "==", s.id))
                  .where(filter=firestore.FieldFilter("placedAt", ">=", now() - timedelta(days=7))).stream()):
            for l in o.to_dict().get("items", []):
                counts[l["itemId"]] = counts.get(l["itemId"], 0) + l["qty"]
        menu_ref = db().collection("cafes").document(s.id).collection("menu")
        for item_id in menu_svc.get_menu(s.id):
            menu_ref.document(item_id).update({"popularity7d": counts.get(item_id, 0)})
        menu_svc.invalidate(s.id)
    return out
