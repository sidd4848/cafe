"""
Situational context for dynamic recommendations: weather at the café and part of day.

Weather comes from Open-Meteo (free, no key; only the café's own coordinates are sent)
and is cached for 15 minutes per café. If it can't be reached, recommendations simply
fall back to time of day. Nothing about the guest is sent anywhere.
"""

import logging
import time

import requests

from app.db import now
from app.services import menu as menu_svc

logger = logging.getLogger(__name__)

_CACHE_SEC = 900
_cache: dict[str, tuple[float, dict | None]] = {}

# WMO weather codes -> (summary, is_wet)
_WMO = {
    0: ("Clear skies", False), 1: ("Mostly clear", False), 2: ("Partly cloudy", False), 3: ("Overcast", False),
    45: ("Foggy", False), 48: ("Foggy", False), 51: ("Light drizzle", True), 53: ("Drizzle", True),
    55: ("Heavy drizzle", True), 61: ("Light rain", True), 63: ("Rainy", True), 65: ("Heavy rain", True),
    80: ("Rain showers", True), 81: ("Rain showers", True), 82: ("Heavy showers", True),
    95: ("Thunderstorms", True), 96: ("Thunderstorms", True), 99: ("Thunderstorms", True),
}


def weather(cafe: dict) -> dict | None:
    hit = _cache.get(cafe["id"])
    if hit and time.monotonic() - hit[0] < _CACHE_SEC:
        return hit[1]
    result = None
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": cafe["lat"], "longitude": cafe["lng"],
                    "current": "temperature_2m,apparent_temperature,precipitation,weather_code"},
            timeout=3,
        )
        r.raise_for_status()
        cur = r.json()["current"]
        summary, wet = _WMO.get(int(cur.get("weather_code", 0)), ("Cloudy", False))
        wet = wet or float(cur.get("precipitation") or 0) > 0.1
        result = {"summary": summary, "tempC": float(cur["temperature_2m"]),
                  "feelsC": float(cur.get("apparent_temperature") or cur["temperature_2m"]), "wet": wet}
    except Exception as e:
        logger.warning(f"Weather unavailable: {e}")
    _cache[cafe["id"]] = (time.monotonic(), result)
    return result


def part_of_day(hour: int) -> str:
    return ("early morning" if hour < 9 else "morning" if hour < 12 else "lunchtime" if hour < 15
            else "afternoon" if hour < 18 else "evening" if hour < 21 else "late evening")


def mood(w: dict | None) -> str:
    """cosy | hot | mild: the weather's pull on what people want."""
    if not w:
        return "mild"
    if w["wet"] or w["feelsC"] < 21:
        return "cosy"
    if w["feelsC"] >= 29:
        return "hot"
    return "mild"


def snapshot(cafe_id: str) -> dict:
    cafe = menu_svc.get_cafe(cafe_id)
    local = now().astimezone(menu_svc.tz(cafe))
    w = weather(cafe)
    m = mood(w)
    pod = part_of_day(local.hour)
    headline = {
        "cosy": "Perfect weather for something warm and comforting.",
        "hot": "It's warm out, so we're leaning iced and light.",
        "mild": f"Good {pod} picks, fresh off the bar.",
    }[m]
    return {"weather": w, "mood": m, "partOfDay": pod, "localHour": local.hour, "headline": headline}


def weather_fit(item: dict, weather_mood: str) -> float:
    """0..1: how well an item suits the weather."""
    tags = set(item.get("tags", []))
    if weather_mood == "cosy":
        if "hot" in tags or {"chocolate", "spiced"} & tags:
            return 1.0
        return 0.2 if "iced" in tags else 0.5
    if weather_mood == "hot":
        if "iced" in tags or {"light", "fizzy", "fruity", "citrus"} & tags:
            return 1.0
        return 0.2 if "hot" in tags else 0.5
    return 0.5
