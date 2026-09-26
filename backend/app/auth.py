"""
Authentication.

Browsers hold Firebase ID tokens, which Cloud Run's IAM layer cannot validate, so the
service is deployed --allow-unauthenticated and verifies tokens here instead.

Roles live in a custom claim `role` (customer | staff | manager). The claim is what the
Firestore rules read, so the API and the realtime listeners agree on who is staff.
"""

import logging

import firebase_admin
from fastapi import Depends, Header, HTTPException
from firebase_admin import auth as firebase_auth
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import FIREBASE_PROJECT_ID, INTERNAL_AUDIENCE, SCHEDULER_SA

logger = logging.getLogger(__name__)

if not firebase_admin._apps:
    firebase_admin.initialize_app(options={"projectId": FIREBASE_PROJECT_ID})

STAFF_ROLES = {"staff", "manager"}


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    return authorization.split(" ", 1)[1]


async def require_user(authorization: str = Header(None)) -> dict:
    try:
        claims = firebase_auth.verify_id_token(_bearer(authorization))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Rejected Firebase ID token: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "uid": claims["uid"],
        "email": (claims.get("email") or "").lower(),
        "email_verified": bool(claims.get("email_verified")),
        "name": claims.get("name") or "",
        "picture": claims.get("picture"),
        "role": claims.get("role", "customer"),
    }


async def require_staff(user: dict = Depends(require_user)) -> dict:
    if user["role"] not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Employee access only")
    return user


async def require_manager(user: dict = Depends(require_user)) -> dict:
    if user["role"] != "manager":
        raise HTTPException(status_code=403, detail="Manager access only")
    return user


async def require_scheduler(authorization: str = Header(None)) -> None:
    """Accept only a Google OIDC token minted for the scheduler SA with our audience."""
    if not INTERNAL_AUDIENCE:
        raise HTTPException(status_code=403, detail="Internal routes are disabled")
    try:
        claims = google_id_token.verify_oauth2_token(
            _bearer(authorization), google_requests.Request(), audience=INTERNAL_AUDIENCE
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Rejected scheduler token: {e}")
        raise HTTPException(status_code=401, detail="Invalid scheduler token")
    if claims.get("email") != SCHEDULER_SA or not claims.get("email_verified"):
        raise HTTPException(status_code=403, detail="Unexpected caller")


def set_role(uid: str, role: str) -> None:
    """Write the role claim, keeping any other claims the account carries."""
    current = firebase_auth.get_user(uid).custom_claims or {}
    firebase_auth.set_custom_user_claims(uid, {**current, "role": role})
