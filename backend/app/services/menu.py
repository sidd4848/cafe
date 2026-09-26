"""
Cafe and menu reads, cached briefly per process.

The menu changes rarely (availability toggles, learned prep times) but is read on every
chat turn, cart edit and ETA recompute, so a short cache saves most of the reads without
serving a toggle stale for long. Writes through this module invalidate it.
"""

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.db import db

_TTL_SEC = 20
_cache: dict[str, tuple[float, dict, dict]] = {}


def _load(cafe_id: str) -> tuple[dict, dict]:
    hit = _cache.get(cafe_id)
    if hit and time.monotonic() - hit[0] < _TTL_SEC:
        return hit[1], hit[2]
    snap = db().collection("cafes").document(cafe_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Cafe not found")
    cafe = {"id": snap.id, **snap.to_dict()}
    items = {
        d.id: {"id": d.id, **d.to_dict()}
        for d in db().collection("cafes").document(cafe_id).collection("menu").stream()
    }
    _cache[cafe_id] = (time.monotonic(), cafe, items)
    return cafe, items


def get_cafe(cafe_id: str) -> dict:
    return _load(cafe_id)[0]


def get_menu(cafe_id: str) -> dict[str, dict]:
    return _load(cafe_id)[1]


def invalidate(cafe_id: str) -> None:
    _cache.pop(cafe_id, None)


def public_item(item: dict) -> dict:
    """Menu item as the UI sees it: no embedding, prep rounded to whole seconds."""
    out = {k: v for k, v in item.items() if k not in {"embedding", "prepSecVar"}}
    out["prepSec"] = round(item.get("prepSecEwma") or item.get("prepSecBase", 120))
    out.pop("prepSecEwma", None)
    return out


# ---- Local time ------------------------------------------------------------------------

def tz(cafe: dict) -> ZoneInfo:
    return ZoneInfo(cafe.get("timezone", "Asia/Kolkata"))


def _hm(value: str) -> tuple[int, int]:
    h, m = value.split(":")
    return int(h), int(m)


def opening_window(cafe: dict, day: datetime) -> tuple[datetime, datetime]:
    """Open and close datetimes (cafe-local, tz-aware) for the local date of `day`."""
    local = day.astimezone(tz(cafe))
    oh, om = _hm(cafe.get("open", "08:00"))
    ch, cm = _hm(cafe.get("close", "23:00"))
    start = local.replace(hour=oh, minute=om, second=0, microsecond=0)
    end = local.replace(hour=ch, minute=cm, second=0, microsecond=0)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def is_open(cafe: dict, at: datetime) -> bool:
    start, end = opening_window(cafe, at)
    return start <= at.astimezone(tz(cafe)) < end
