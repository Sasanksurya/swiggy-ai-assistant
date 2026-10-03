"""Tool handlers for the Mock Swiggy MCP.

These mirror ONLY the SwiggyPlatform interface used by this application.
They are not a copy of any real Swiggy tool schema.
"""
from __future__ import annotations

from typing import Any

from .data import DELIVERY_FEE_INR, MENUS, ORDERS, RESTAURANTS

_CARTS: dict[str, dict[str, int]] = {}


class ToolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def reset_state() -> None:
    _CARTS.clear()


def _all_items() -> dict[str, dict]:
    return {i["id"]: i for items in MENUS.values() for i in items}


def _restaurant(rid: str) -> dict:
    for r in RESTAURANTS:
        if r["id"] == rid:
            return r
    raise ToolError("not_found", f"Restaurant {rid} not found")


def search_restaurants(query: str = "", cuisine: str | None = None,
                       max_price_for_two_inr: int | None = None, open_only: bool = False) -> list[dict]:
    q = query.strip().lower()
    out = []
    for r in RESTAURANTS:
        hay = " ".join([r["name"], *r["cuisines"], r["area"]]).lower()
        if q and q not in hay:
            continue
        if cuisine and cuisine.lower() not in [c.lower() for c in r["cuisines"]]:
            continue
        if max_price_for_two_inr is not None and r["price_for_two_inr"] > max_price_for_two_inr:
            continue
        if open_only and not r["is_open"]:
            continue
        out.append(r)
    return out


def get_restaurant_details(restaurant_id: str) -> dict:
    return _restaurant(restaurant_id)


def get_menu(restaurant_id: str) -> dict:
    r = _restaurant(restaurant_id)
    return {"restaurant": r, "items": MENUS.get(restaurant_id, [])}


def search_menu(query: str = "", restaurant_id: str | None = None, max_price_inr: int | None = None,
                veg_only: bool = False, available_only: bool = True) -> list[dict]:
    q = query.strip().lower()
    out = []
    for rid, items in MENUS.items():
        if restaurant_id and rid != restaurant_id:
            continue
        for i in items:
            if q and q not in f"{i['name']} {i['category']}".lower():
                continue
            if max_price_inr is not None and i["price_inr"] > max_price_inr:
                continue
            if veg_only and not i["veg"]:
                continue
            if available_only and not i["available"]:
                continue
            out.append(i)
    return out


def get_item_details(item_id: str) -> dict:
    item = _all_items().get(item_id)
    if not item:
        raise ToolError("not_found", f"Item {item_id} not found")
    return item


def _cart_view(session_id: str) -> dict:
    cart = _CARTS.get(session_id, {})
    items = _all_items()
    lines, subtotal, rid = [], 0, None
    for item_id, qty in cart.items():
        it = items[item_id]
        rid = it["restaurant_id"]
        line_total = it["price_inr"] * qty
        subtotal += line_total
        lines.append({"item_id": item_id, "name": it["name"], "quantity": qty,
                      "unit_price_inr": it["price_inr"], "line_total_inr": line_total})
    fee = DELIVERY_FEE_INR if lines else 0
    return {"session_id": session_id, "restaurant_id": rid, "lines": lines,
            "subtotal_inr": subtotal, "delivery_fee_inr": fee, "total_inr": subtotal + fee}


def get_cart(session_id: str = "default") -> dict:
    return _cart_view(session_id)


def add_to_cart(item_id: str, quantity: int = 1, session_id: str = "default") -> dict:
    if quantity < 1:
        raise ToolError("invalid_argument", "quantity must be >= 1")
    item = get_item_details(item_id)
    if not item["available"]:
        raise ToolError("item_unavailable", f"{item['name']} is not available")
    cart = _CARTS.setdefault(session_id, {})
    if cart:
        existing_rid = _all_items()[next(iter(cart))]["restaurant_id"]
        if existing_rid != item["restaurant_id"]:
            raise ToolError("restaurant_conflict", "Cart already has items from another restaurant")
    cart[item_id] = cart.get(item_id, 0) + quantity
    return _cart_view(session_id)


def update_cart(item_id: str, quantity: int, session_id: str = "default") -> dict:
    cart = _CARTS.get(session_id, {})
    if item_id not in cart:
        raise ToolError("not_found", f"Item {item_id} is not in the cart")
    if quantity < 1:
        raise ToolError("invalid_argument", "quantity must be >= 1 (use remove_from_cart to delete)")
    cart[item_id] = quantity
    return _cart_view(session_id)


def remove_from_cart(item_id: str, session_id: str = "default") -> dict:
    cart = _CARTS.get(session_id, {})
    if item_id not in cart:
        raise ToolError("not_found", f"Item {item_id} is not in the cart")
    del cart[item_id]
    if not cart:
        _CARTS.pop(session_id, None)
    return _cart_view(session_id)


def get_order_status(order_id: str) -> dict:
    o = ORDERS.get(order_id)
    if not o:
        raise ToolError("not_found", f"Order {order_id} not found")
    return {"order_id": order_id, "status": o["status"]}


def get_order_details(order_id: str) -> dict:
    o = ORDERS.get(order_id)
    if not o:
        raise ToolError("not_found", f"Order {order_id} not found")
    return o


TOOLS: dict[str, Any] = {
    f.__name__: f for f in (
        search_restaurants, get_restaurant_details, search_menu, get_menu, get_item_details,
        get_cart, add_to_cart, update_cart, remove_from_cart, get_order_status, get_order_details,
    )
}
