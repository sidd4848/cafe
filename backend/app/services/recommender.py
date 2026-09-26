"""
Personalised recommendations.

score = 0.33 x cosine(taste, item)       semantic match to what you like (order history)
      + 0.20 x preference match          explicit quiz answers against item tags
      + 0.10 x time-of-day fit           breakfast in the morning, no strong coffee late
      + 0.10 x weather fit               warm & comforting when it rains, iced & light when hot
      + 0.08 x popularity                what the cafe sells a lot of this week
      + 0.07 x novelty                   not something you've had in the last 14 days
      + 0.07 x price comfort             near what this guest usually spends (loyalty profile)
      + 0.05 x pairing                   food with a drink-only cart, and vice versa

The taste vector is a weighted mean of the quiz embedding and the embeddings of items
you ordered, liked or dismissed (dismissals push away), decayed with a 30-day half-life.
Hard constraints (diet, allergens, dislikes) are filters in code, never just a prompt.
"""

import logging
import math
import time
from datetime import datetime

from google.cloud import firestore

from app.db import db, now
from app.services import context as context_svc
from app.services import llm
from app.services import menu as menu_svc

logger = logging.getLogger(__name__)

WEIGHTS = {"order": 1.0, "like": 0.6, "view": 0.1, "dismiss": -0.4}
HALF_LIFE_DAYS = 30
DRINKS = {"hot_coffee", "manual_brew", "cold_coffee", "not_coffee"}

_reason_cache: dict[tuple, tuple[float, str]] = {}


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def prefs_text(prefs: dict) -> str:
    parts = []
    if prefs.get("temperature") in {"hot", "iced"}:
        parts.append(f"prefers {prefs['temperature']} drinks")
    sweet = {0: "unsweetened", 1: "lightly sweet", 2: "sweet", 3: "very sweet, dessert-like"}
    if prefs.get("sweetness") is not None:
        parts.append(sweet.get(int(prefs["sweetness"]), "sweet"))
    if prefs.get("milk"):
        parts.append("black coffee" if prefs["milk"] == "none" else f"{prefs['milk']} milk")
    caffeine = {"none": "caffeine-free", "light": "mild, low caffeine",
                "regular": "regular coffee strength", "strong": "strong, bold coffee"}
    if prefs.get("caffeine"):
        parts.append(caffeine.get(prefs["caffeine"], ""))
    if prefs.get("flavours"):
        parts.append("likes " + ", ".join(prefs["flavours"]) + " flavours")
    return "; ".join(p for p in parts if p) or "open to anything"


def allowed(item: dict, prefs: dict) -> bool:
    if not item.get("available", True):
        return False
    if item["id"] in set(prefs.get("dislikes") or []):
        return False
    dietary = set(item.get("dietary", []))
    diet = prefs.get("diet", "any")
    avoid = set(prefs.get("avoid") or [])
    if diet in {"veg", "vegan"} and "non_veg" in dietary:
        return False
    plant_milk_ok = "milk" in item.get("modifiers", [])
    needs_no_dairy = diet == "vegan" or "dairy" in avoid
    if needs_no_dairy and "dairy" in dietary and not plant_milk_ok:
        return False
    if diet == "vegan" and "egg" in dietary:
        return False
    return not (avoid - {"dairy"}) & dietary


def _pref_match(item: dict, prefs: dict) -> float:
    tags = set(item.get("tags", []))
    score, n = 0.0, 0
    temp = prefs.get("temperature")
    if temp in {"hot", "iced"} and item["category"] in DRINKS:
        n += 1
        score += 1.0 if temp in tags else 0.0
    sweet = prefs.get("sweetness")
    if sweet is not None:
        n += 1
        is_sweet = "sweet" in tags
        score += 1.0 if (int(sweet) >= 2) == is_sweet else 0.3
    caffeine = prefs.get("caffeine")
    if caffeine and item["category"] in DRINKS:
        n += 1
        if caffeine == "none":
            score += 1.0 if "caffeine_free" in tags else 0.0
        elif caffeine == "strong":
            score += 1.0 if "strong" in tags else 0.3
        elif caffeine == "light":
            score += 1.0 if {"caffeine_light", "caffeine_free", "mild"} & tags else 0.3
        else:
            score += 0.7
    flavours = set(prefs.get("flavours") or [])
    if flavours:
        n += 1
        score += min(1.0, len(flavours & tags) / 1.0)
    if prefs.get("milk") == "none" and item["category"] in DRINKS:
        n += 1
        score += 1.0 if "black" in tags else 0.2
    return score / n if n else 0.5


def _time_fit(item: dict, local_hour: int, prefs: dict) -> float:
    tags = set(item.get("tags", []))
    fit = 0.5
    if local_hour < 11 and "breakfast" in tags:
        fit += 0.4
    if 12 <= local_hour < 15 and "lunch" in tags:
        fit += 0.4
    if local_hour >= 15 and {"dessert", "sweet"} & tags:
        fit += 0.2
    if local_hour >= 18 and "strong" in tags and prefs.get("caffeine") != "strong":
        fit -= 0.4
    if local_hour >= 19 and "caffeine_free" in tags:
        fit += 0.3
    return max(0.0, min(1.0, fit))


def taste_vector(uid: str, user: dict, menu: dict) -> list[float] | None:
    acc: list[float] | None = None
    total_w = 0.0

    def add(vec, w):
        nonlocal acc, total_w
        if not vec:
            return
        if acc is None:
            acc = [0.0] * len(vec)
        for i, x in enumerate(vec):
            acc[i] += w * x
        total_w += abs(w)

    add(user.get("prefsEmbedding"), 2.0)
    t = now()
    events = (db().collection("users").document(uid).collection("interactions")
              .order_by("at", direction=firestore.Query.DESCENDING).limit(100).stream())
    for s in events:
        e = s.to_dict()
        item = menu.get(e.get("itemId"))
        at = e.get("at")
        if not item or not isinstance(at, datetime):
            continue
        decay = 0.5 ** ((t - at).days / HALF_LIFE_DAYS)
        add(item.get("embedding"), WEIGHTS.get(e.get("type"), 0) * decay)
    if acc is None or total_w == 0:
        return None
    return [x / total_w for x in acc]


def _recent_orders(uid: str) -> dict[str, int]:
    """itemId -> times ordered in the last 14 days."""
    counts: dict[str, int] = {}
    since = time.time() - 14 * 86400
    for s in (db().collection("users").document(uid).collection("interactions")
              .where(filter=firestore.FieldFilter("type", "==", "order"))
              .limit(200).stream()):
        e = s.to_dict()
        at = e.get("at")
        if isinstance(at, datetime) and at.timestamp() >= since:
            counts[e["itemId"]] = counts.get(e["itemId"], 0) + 1
    return counts


def _price_comfort(item: dict, avg_ticket: int) -> float:
    if not avg_ticket:
        return 0.5
    over = max(0, item["price"] - 0.8 * avg_ticket)
    return 1.0 - min(1.0, over / avg_ticket)


def _reasons(user: dict, picks: list[dict], local_hour: int, ctx: dict | None = None) -> dict[str, str]:
    key_user = user.get("uid")
    out, missing = {}, []
    for p in picks:
        hit = _reason_cache.get((key_user, p["id"]))
        if hit and time.time() - hit[0] < 6 * 3600:
            out[p["id"]] = hit[1]
        else:
            missing.append(p)
    if missing:
        prompt = (
            f"Guest taste: {prefs_text(user.get('prefs') or {})}. Local hour: {local_hour}.\n"
            "For each item write one warm, specific reason (max 14 words) this guest would enjoy it. "
            "No emojis, don't repeat the item name.\n"
            + "\n".join(f"- {p['id']}: {p['name']} - {p['description']}" for p in missing)
        )
        schema = {"type": "OBJECT", "properties": {"reasons": {"type": "ARRAY", "items": {
            "type": "OBJECT", "properties": {"id": {"type": "STRING"}, "reason": {"type": "STRING"}},
            "required": ["id", "reason"]}}}, "required": ["reasons"]}
        try:
            result = llm.generate_json("You are a friendly specialty-coffee barista.", prompt, schema, 0.7)
            for r in result.get("reasons", []):
                out[r["id"]] = r["reason"]
                _reason_cache[(key_user, r["id"])] = (time.time(), r["reason"])
        except Exception as e:
            logger.warning(f"Reason generation failed: {e}")
    for p in picks:
        out.setdefault(p["id"], p["description"])
    return out


def recommend(cafe_id: str, uid: str, user: dict, n: int = 6,
              cart_item_ids: list[str] | None = None, with_reasons: bool = True) -> list[dict]:
    cafe = menu_svc.get_cafe(cafe_id)
    menu = menu_svc.get_menu(cafe_id)
    prefs = user.get("prefs") or {}
    local_hour = now().astimezone(menu_svc.tz(cafe)).hour
    ctx = context_svc.snapshot(cafe_id)
    avg_ticket = int((user.get("loyalty") or {}).get("avgTicket", 0))
    taste = taste_vector(uid, user, menu)
    recent = _recent_orders(uid)
    max_pop = max([i.get("popularity7d", 0) for i in menu.values()] + [1])
    cart_cats = {menu[i]["category"] for i in (cart_item_ids or []) if i in menu}
    cart_has_drink = bool(cart_cats & DRINKS)
    cart_has_food = bool(cart_cats - DRINKS)

    scored = []
    for item in menu.values():
        if not allowed(item, prefs) or item["id"] in (cart_item_ids or []):
            continue
        cos = _cos(taste, item["embedding"]) if taste and item.get("embedding") else 0.5
        pairing = 1.0 if (cart_has_drink and item["category"] not in DRINKS) or \
                         (cart_has_food and item["category"] in DRINKS) else 0.0
        score = (0.33 * cos + 0.20 * _pref_match(item, prefs)
                 + 0.10 * _time_fit(item, local_hour, prefs)
                 + 0.10 * context_svc.weather_fit(item, ctx["mood"])
                 + 0.08 * item.get("popularity7d", 0) / max_pop
                 + 0.07 * (0.0 if recent.get(item["id"]) else 1.0)
                 + 0.07 * _price_comfort(item, avg_ticket)
                 + 0.05 * pairing)
        scored.append((score, item))
    scored.sort(key=lambda s: s[0], reverse=True)

    # Keep the list varied: at most two per category, and at least one food pick.
    picks, per_cat = [], {}
    for score, item in scored:
        if per_cat.get(item["category"], 0) >= 2:
            continue
        picks.append((score, item))
        per_cat[item["category"]] = per_cat.get(item["category"], 0) + 1
        if len(picks) >= n:
            break
    if picks and not any(i["category"] not in DRINKS for _, i in picks):
        food = next(((s, i) for s, i in scored if i["category"] not in DRINKS), None)
        if food:
            picks[-1] = food

    items = [i for _, i in picks]
    reasons = _reasons({"uid": uid, **user}, items, local_hour, ctx) if with_reasons else {}
    vegan_swap = prefs.get("diet") == "vegan" or "dairy" in (prefs.get("avoid") or [])
    return [{
        "item": menu_svc.public_item(i),
        "score": round(s, 3),
        "reason": reasons.get(i["id"], i["description"]),
        "suggestedModifiers": ({"milk": "oat"} if vegan_swap and "milk" in i.get("modifiers", [])
                               else {"milk": prefs["milk"]} if prefs.get("milk") not in (None, "none", "dairy")
                               and "milk" in i.get("modifiers", []) else {}),
    } for s, i in picks]
