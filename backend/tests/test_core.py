"""Pure-logic tests: cart validation and the ETA prep model. No Firestore or Gemini."""

import pytest

from app.menu_data import MENU
from app.services import cart, eta

M = {i["id"]: {**i, "available": True} for i in MENU}


def test_line_prices_modifiers_and_defaults():
    line = cart.build_line(M, "cafe_latte", 2, {"milk": "oat milk", "size": "big"})
    assert line["modifiers"] == {"size": "large", "milk": "oat", "shot": "none", "sweetness": "regular"}
    assert line["unitPrice"] == 25000 + 4000 + 6000
    assert line["lineTotal"] == 2 * line["unitPrice"]


def test_rejects_unknown_item_and_wrong_modifier():
    with pytest.raises(cart.CartError):
        cart.build_line(M, "unicorn_latte")
    with pytest.raises(cart.CartError, match="doesn't take"):
        cart.build_line(M, "espresso", 1, {"milk": "oat"})
    with pytest.raises(cart.CartError, match="isn't a milk option"):
        cart.build_line(M, "cafe_latte", 1, {"milk": "camel"})


def test_unavailable_item_blocked():
    menu = {**M, "mocha": {**M["mocha"], "available": False}}
    with pytest.raises(cart.CartError, match="not available"):
        cart.build_line(menu, "mocha")


def test_add_merges_identical_lines():
    c = cart.apply_op([], M, {"op": "add", "itemId": "espresso"})
    c = cart.apply_op(c, M, {"op": "add", "itemId": "espresso", "qty": 2})
    assert len(c) == 1 and c[0]["qty"] == 3


def test_order_prep_batches_within_an_order():
    one, _ = eta.order_prep({"items": [{"itemId": "cappuccino", "qty": 1}]}, M)
    two, _ = eta.order_prep({"items": [{"itemId": "cappuccino", "qty": 2}]}, M)
    assert one == 140
    assert two == pytest.approx(140 * (1 + eta.BATCH_FACTOR))
