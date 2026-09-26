"""
Conversational ordering.

Gemini gets the live menu, the guest's saved preferences and usuals, the current cart and
a set of tools. It can only change the cart by calling those tools, and every call is
validated by services/cart.py against the menu, so a hallucinated item or price never
reaches the cart. Placing (and paying for) the order is a button in the UI, not a tool:
the model can build the order but never submit it.
"""

import json
import logging
from datetime import datetime, timedelta

from google.genai import types

from app.config import GEMINI_MODEL
from app.db import now
from app.menu_data import MODIFIERS
from app.services import cart as cart_svc
from app.services import llm
from app.services import menu as menu_svc
from app.services import recommender

logger = logging.getLogger(__name__)

MAX_STEPS = 6
HISTORY_TURNS = 20

PREF_KEYS = {"milk", "sweetness", "caffeine", "temperature", "diet", "avoid"}


def _fn(name, description, props=None, required=None):
    return types.FunctionDeclaration(
        name=name, description=description,
        parameters=types.Schema(type="OBJECT", properties=props or {}, required=required or []),
    )


S = lambda d, **kw: types.Schema(type="STRING", description=d, **kw)  # noqa: E731
MODS = types.Schema(
    type="OBJECT",
    description="Modifier choices by group id, e.g. {\"milk\": \"oat\", \"size\": \"large\"}.",
    properties={g: types.Schema(type="STRING", enum=[o["id"] for o in m["options"]])
                for g, m in MODIFIERS.items()},
)

TOOLS = types.Tool(function_declarations=[
    _fn("add_to_cart", "Add a menu item to the cart.",
        {"item_id": S("Menu item id"), "qty": types.Schema(type="INTEGER"), "modifiers": MODS},
        ["item_id"]),
    _fn("update_cart_line", "Change quantity or modifiers of an existing cart line.",
        {"line_id": S("Cart line id"), "qty": types.Schema(type="INTEGER"), "modifiers": MODS},
        ["line_id"]),
    _fn("remove_from_cart", "Remove a cart line.", {"line_id": S("Cart line id")}, ["line_id"]),
    _fn("clear_cart", "Empty the cart."),
    _fn("get_recommendations", "Personalised picks for this guest right now."),
    _fn("get_wait_time", "Current wait at the counter and how many orders are ahead."),
    _fn("set_pickup_time",
        "Pre-order: set when the guest wants to collect. Use minutes_from_now for "
        "'I'm 10 minutes away', or local_time 'HH:MM' for a clock time today. "
        "Pass neither to clear it (collect as soon as possible).",
        {"minutes_from_now": types.Schema(type="INTEGER"), "local_time": S("24h HH:MM")}),
    _fn("save_preference",
        "Remember a stated preference for future visits. Only when the guest states it "
        "as a lasting preference ('I'm vegan', 'I always take oat milk').",
        {"key": S("Preference key", enum=sorted(PREF_KEYS)), "value": S("Value")},
        ["key", "value"]),
])


def _menu_block(menu: dict) -> str:
    rows = []
    for i in sorted(menu.values(), key=lambda x: (x["category"], x["price"])):
        if not i.get("available", True):
            continue
        rows.append(f"{i['id']} | {i['name']} | Rs {i['price'] // 100} | {i['category']} | "
                    f"tags: {', '.join(i['tags'])} | diet: {', '.join(i['dietary'])} | "
                    f"options: {', '.join(i['modifiers']) or 'none'}")
    return "\n".join(rows)


def _mods_block() -> str:
    return "\n".join(
        f"{g}: " + ", ".join(f"{o['id']}" + (f" (+Rs {o['delta'] // 100})" if o["delta"] else "")
                             for o in m["options"])
        for g, m in MODIFIERS.items())


def _system(cafe: dict, menu: dict, user: dict, session: dict) -> str:
    local = now().astimezone(menu_svc.tz(cafe))
    prefs = user.get("prefs") or {}
    usuals = user.get("usuals") or []
    usual_txt = "; ".join(f"{u['name']} ({', '.join(u.get('modifierLabels') or []) or 'standard'})"
                          for u in usuals[:3]) or "none yet"
    pickup = session.get("pickupAt")
    return f"""You are the friendly barista at {cafe['name']}, taking orders in a chat.
Local time: {local.strftime('%A %H:%M')}. Open {cafe.get('open')}-{cafe.get('close')}. Prices in Indian rupees.

Guest: {user.get('displayName') or 'guest'}
Saved preferences: {json.dumps(prefs) if prefs else 'none'} ({recommender.prefs_text(prefs)})
Their usual: {usual_txt}

MENU (id | name | price | category | tags | diet | option groups):
{_menu_block(menu)}

OPTION GROUPS (first option is the default):
{_mods_block()}

CURRENT CART:
{cart_svc.describe(session.get('cart') or [])}
Pickup: {pickup.astimezone(menu_svc.tz(cafe)).strftime('%H:%M') if isinstance(pickup, datetime) else 'as soon as possible'}

How to behave:
- Use the tools to change the cart; never claim a change you didn't make with a tool.
- Apply saved preferences automatically (e.g. their milk choice) and say so briefly.
- Respect diet/allergen preferences strictly. A vegan guest's milk drinks need a plant milk.
- If a request is vague ("something cold and not too sweet"), suggest 2-3 real menu items
  with one line each, or call get_recommendations.
- "The usual" means their usual above.
- For "I'll be there in 15 min" or "for 5:30pm", call set_pickup_time; the order will be
  timed to be ready then.
- You cannot place or pay for the order. When the cart looks complete, tell them to tap
  "Checkout". Do NOT state totals, item counts or do any arithmetic yourself: the app shows
  the exact cart and total. Only mention an individual item's menu price if asked.
- Keep replies short (1-3 sentences), warm, no markdown headings, no emojis."""


def _usual_line(user: dict) -> dict | None:
    usuals = user.get("usuals") or []
    return usuals[0] if usuals else None


def run_turn(cafe_id: str, uid: str, user: dict, session: dict, text: str,
             on_pref: callable) -> dict:
    """Run one guest message through the agent. Returns the updated session fields."""
    cafe = menu_svc.get_cafe(cafe_id)
    menu = menu_svc.get_menu(cafe_id)
    cart = list(session.get("cart") or [])
    pickup_at = session.get("pickupAt")
    actions: list[str] = []

    history = []
    for m in (session.get("messages") or [])[-HISTORY_TURNS:]:
        history.append(types.Content(role="user" if m["role"] == "user" else "model",
                                     parts=[types.Part(text=m["text"])]))
    history.append(types.Content(role="user", parts=[types.Part(text=text)]))

    def call(name: str, args: dict) -> dict:
        nonlocal cart, pickup_at
        try:
            if name == "add_to_cart":
                cart = cart_svc.apply_op(cart, menu, {"op": "add", "itemId": args.get("item_id"),
                                                      "qty": args.get("qty", 1),
                                                      "modifiers": args.get("modifiers")})
                actions.append(f"Added {menu[args['item_id']]['name']}")
            elif name == "update_cart_line":
                cart = cart_svc.apply_op(cart, menu, {"op": "update", "lineId": args.get("line_id"),
                                                      "qty": args.get("qty"), "modifiers": args.get("modifiers")}
                                         if args.get("qty") else
                                         {"op": "update", "lineId": args.get("line_id"),
                                          "modifiers": args.get("modifiers")})
                actions.append("Updated cart")
            elif name == "remove_from_cart":
                cart = cart_svc.apply_op(cart, menu, {"op": "remove", "lineId": args.get("line_id")})
                actions.append("Removed an item")
            elif name == "clear_cart":
                cart = []
                actions.append("Cleared cart")
            elif name == "get_recommendations":
                recs = recommender.recommend(cafe_id, uid, user, n=4,
                                             cart_item_ids=[l["itemId"] for l in cart], with_reasons=False)
                return {"recommendations": [{"id": r["item"]["id"], "name": r["item"]["name"],
                                             "price_rs": r["item"]["price"] // 100,
                                             "why": r["item"]["description"]} for r in recs]}
            elif name == "get_wait_time":
                from app.db import db
                snap = db().collection("cafes").document(cafe_id).collection("stats").document("live").get()
                live = snap.to_dict() if snap.exists else {}
                return {"wait_minutes": round((live.get("currentWaitSec") or 180) / 60),
                        "orders_ahead": live.get("activeOrders", 0)}
            elif name == "set_pickup_time":
                local_now = now().astimezone(menu_svc.tz(cafe))
                if args.get("minutes_from_now"):
                    pickup_at = now() + timedelta(minutes=int(args["minutes_from_now"]))
                elif args.get("local_time"):
                    h, m = map(int, str(args["local_time"]).split(":"))
                    target = local_now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if target < local_now:
                        return {"error": "That time has already passed today."}
                    pickup_at = target
                else:
                    pickup_at = None
                if pickup_at and not menu_svc.is_open(cafe, pickup_at):
                    pickup_at = None
                    return {"error": f"We're only open {cafe.get('open')}-{cafe.get('close')}."}
                actions.append("Set pickup time" if pickup_at else "Pickup set to ASAP")
                return {"ok": True, "pickup_local": pickup_at.astimezone(menu_svc.tz(cafe)).strftime("%H:%M")
                        if pickup_at else "asap"}
            elif name == "save_preference":
                key, value = args.get("key"), args.get("value")
                if key not in PREF_KEYS:
                    return {"error": "Unknown preference"}
                on_pref(key, value)
                actions.append(f"Saved preference: {key}")
                return {"ok": True}
            else:
                return {"error": f"Unknown tool {name}"}
        except cart_svc.CartError as e:
            return {"error": str(e)}
        except (KeyError, ValueError, TypeError) as e:
            return {"error": f"Bad arguments: {e}"}
        return {"ok": True, "cart": cart_svc.describe(cart),
                "item_count": sum(l["qty"] for l in cart), "total_rs": cart_svc.total(cart) // 100}

    reply = ""
    for _ in range(MAX_STEPS):
        response = llm.client().models.generate_content(
            model=GEMINI_MODEL,
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=_system(cafe, menu, user, {"cart": cart, "pickupAt": pickup_at}),
                tools=[TOOLS],
                temperature=0.5,
                automatic_function_calling=llm.NO_AFC,
            ),
        )
        calls = response.function_calls or []
        if not calls:
            reply = (response.text or "").strip()
            break
        # Echo the model turn back verbatim: it carries the thought signatures Gemini 3
        # needs to continue a tool-calling turn.
        history.append(response.candidates[0].content)
        history.append(types.Content(role="user", parts=[
            types.Part.from_function_response(name=c.name, response=call(c.name, dict(c.args or {})))
            for c in calls
        ]))
    if not reply:
        reply = "Done! Anything else, or shall we check out?"

    return {"cart": cart, "pickupAt": pickup_at, "reply": reply, "actions": actions}
