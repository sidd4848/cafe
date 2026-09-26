"""
Cart validation and pricing.

This is the only code that turns "an item with some modifiers" into a priced cart line.
Both the menu UI and the ordering agent go through it, so the language model can never
invent an item, a modifier or a price: anything it asks for is resolved against the menu
here, and a precise error goes back to it when the request doesn't fit.
"""

import secrets

from app.menu_data import MODIFIERS

MAX_QTY = 10
MAX_LINES = 20


class CartError(ValueError):
    pass


def _match_option(group: str, wanted) -> dict | None:
    wanted = str(wanted).strip().lower().replace(" milk", "").replace("-", "_")
    for opt in MODIFIERS[group]["options"]:
        if wanted in {opt["id"], opt["label"].lower()}:
            return opt
    # Common phrasings the model or a user reaches for.
    aliases = {
        "milk": {"whole": "dairy", "regular": "dairy", "full_cream": "dairy", "normal": "dairy"},
        "size": {"small": "regular", "medium": "regular", "big": "large", "l": "large"},
        "shot": {"yes": "extra", "double": "extra", "extra_shot": "extra", "no": "none"},
        "sweetness": {"low": "less", "sugar_free": "none", "unsweetened": "none"},
        "warm": {"warmed": "yes", "hot": "yes", "cold": "no"},
    }
    alias = aliases.get(group, {}).get(wanted)
    if alias:
        return next(o for o in MODIFIERS[group]["options"] if o["id"] == alias)
    return None


def build_line(menu: dict, item_id: str, qty: int = 1, modifiers: dict | None = None,
               line_id: str | None = None) -> dict:
    item = menu.get(item_id)
    if not item:
        raise CartError(f"Unknown item '{item_id}'. Use an id from the menu.")
    if not item.get("available", True):
        raise CartError(f"{item['name']} is not available right now.")
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        raise CartError("Quantity must be a whole number.")
    if not 1 <= qty <= MAX_QTY:
        raise CartError(f"Quantity must be between 1 and {MAX_QTY}.")

    allowed = item.get("modifiers", [])
    chosen: dict[str, str] = {}
    labels: list[str] = []
    delta = 0
    for group, value in (modifiers or {}).items():
        if value in (None, ""):
            continue
        if group not in allowed:
            raise CartError(
                f"{item['name']} doesn't take a '{group}' option. "
                f"Allowed: {', '.join(allowed) or 'none'}."
            )
        opt = _match_option(group, value)
        if not opt:
            valid = ", ".join(o["id"] for o in MODIFIERS[group]["options"])
            raise CartError(f"'{value}' isn't a {group} option. Choose one of: {valid}.")
        chosen[group] = opt["id"]
    for group in allowed:
        opt = next(o for o in MODIFIERS[group]["options"] if o["id"] == chosen.get(group, MODIFIERS[group]["options"][0]["id"]))
        chosen[group] = opt["id"]
        delta += opt["delta"]
        if opt is not MODIFIERS[group]["options"][0]:
            labels.append(opt["label"])

    unit = item["price"] + delta
    return {
        "lineId": line_id or secrets.token_hex(4),
        "itemId": item_id,
        "name": item["name"],
        "qty": qty,
        "modifiers": chosen,
        "modifierLabels": labels,
        "unitPrice": unit,
        "lineTotal": unit * qty,
    }


def apply_op(cart: list[dict], menu: dict, op: dict) -> list[dict]:
    """Apply one cart operation and return the new cart. Raises CartError when invalid."""
    kind = op.get("op")
    cart = list(cart)
    if kind == "add":
        if len(cart) >= MAX_LINES:
            raise CartError("The cart is full.")
        new = build_line(menu, op.get("itemId"), op.get("qty", 1), op.get("modifiers"))
        # Merge with an identical line rather than listing the same drink twice.
        for i, line in enumerate(cart):
            if line["itemId"] == new["itemId"] and line["modifiers"] == new["modifiers"]:
                cart[i] = build_line(menu, line["itemId"], min(MAX_QTY, line["qty"] + new["qty"]),
                                     line["modifiers"], line["lineId"])
                return cart
        cart.append(new)
        return cart

    idx = next((i for i, l in enumerate(cart) if l["lineId"] == op.get("lineId")), None)
    if kind in {"update", "remove"} and idx is None:
        raise CartError(f"No cart line '{op.get('lineId')}'.")
    if kind == "update":
        line = cart[idx]
        mods = {**line["modifiers"], **(op.get("modifiers") or {})}
        cart[idx] = build_line(menu, line["itemId"], op.get("qty", line["qty"]), mods, line["lineId"])
        return cart
    if kind == "remove":
        cart.pop(idx)
        return cart
    if kind == "clear":
        return []
    raise CartError(f"Unknown cart operation '{kind}'.")


def reprice(cart: list[dict], menu: dict) -> list[dict]:
    """Re-validate a stored cart against the current menu (prices, availability)."""
    return [build_line(menu, l["itemId"], l["qty"], l["modifiers"], l["lineId"]) for l in cart]


def total(cart: list[dict]) -> int:
    return sum(l["lineTotal"] for l in cart)


def describe(cart: list[dict]) -> str:
    if not cart:
        return "(empty)"
    rows = []
    for l in cart:
        mods = f" [{', '.join(l['modifierLabels'])}]" if l["modifierLabels"] else ""
        rows.append(f"- line {l['lineId']}: {l['qty']} x {l['name']}{mods} = Rs {l['lineTotal'] // 100}")
    rows.append(f"Total: Rs {total(cart) // 100}")
    return "\n".join(rows)
