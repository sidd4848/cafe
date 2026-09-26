"""Firestore client bound to the app's named database, plus small time helpers."""

from datetime import datetime, timezone
from functools import lru_cache

from google.cloud import firestore

from app.config import FIRESTORE_DB, PROJECT_ID


@lru_cache(maxsize=1)
def db() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID, database=FIRESTORE_DB)


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value) -> str | None:
    """Firestore timestamps come back as datetimes; the API speaks ISO-8601."""
    return value.isoformat() if isinstance(value, datetime) else value


def serialize(data: dict) -> dict:
    """Convert every datetime in a document (one level of nesting deep) to ISO strings."""
    out = {}
    for k, v in data.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, dict):
            out[k] = {kk: iso(vv) for kk, vv in v.items()}
        else:
            out[k] = v
    return out
