"""Turns Swiggy's real read-only responses into the shapes the rest of the app uses.

The response shapes here were recorded from the real server with the doctor command (docs/SWIGGY_ACCESS.md).
The mapping is fail-closed: a row that lacks a field the agent needs is dropped, and a payload that is not the
expected shape raises MappingError. Nothing is guessed, defaulted or invented, and personal data in the raw
response (phone numbers, coordinates) is never copied through.
"""
from __future__ import annotations

import re
from typing import Any


class MappingError(Exception):
    """Swiggy answered, but not in a shape this version understands."""


def _text(v: Any) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() else None


def _ident(v: Any) -> str | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return str(v)
    return _text(v)


def _rupees(v: Any) -> int | None:
    """A whole, non-negative rupee amount from a number. Anything else (text, paise, None) is not a price."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(v) if v >= 0 and float(v).is_integer() else None


def parse_rupees(text: Any) -> int | None:
    """'₹500 for two' -> 500. Returns None when there is no clear single amount."""
    m = re.fullmatch(r"\s*₹\s*([\d,]+)(?:\s+for\s+two)?\s*", text) if isinstance(text, str) else None
    return int(m.group(1).replace(",", "")) if m else None


def _minutes(v: Any) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def _rating(v: Any) -> float | None:
    """Ratings arrive as a number or a numeric string; anything else means 'no rating'."""
    try:
        r = float(v)
    except (TypeError, ValueError):
        return None
    return r if 0 <= r <= 5 and not isinstance(v, bool) else None


def _cuisines(v: Any) -> list[str]:
    return [c.strip() for c in v if isinstance(c, str) and c.strip()] if isinstance(v, list) else []


def _name_and_ad(name: str) -> tuple[str, bool]:
    clean = re.sub(r"\s*\(Ad\)\s*$", "", name)
    return clean, clean != name


def _restaurant(raw: Any, *, open_value: Any, minutes: Any, price: Any, area: Any, rating: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    rid, name = _ident(raw.get("id")), _text(raw.get("name"))
    price_inr, mins = parse_rupees(price), _minutes(minutes)
    if rid is None or name is None or price_inr is None or mins is None or not isinstance(open_value, bool):
        return None
    name, sponsored = _name_and_ad(name)
    return {"id": rid, "name": name, "cuisines": _cuisines(raw.get("cuisines")), "area": _text(area) or "",
            "rating": _rating(rating), "delivery_time_min": mins, "price_for_two_inr": price_inr,
            "is_open": open_value, "sponsored": sponsored}


def map_restaurants(payload: Any) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("restaurants"), list):
        raise MappingError("search_restaurants: expected an object with a 'restaurants' list")
    out = []
    for raw in payload["restaurants"]:
        if not isinstance(raw, dict):
            continue
        status = raw.get("availabilityStatus")
        mapped = _restaurant(raw, open_value=(status == "OPEN") if isinstance(status, str) else None,
                             minutes=raw.get("deliveryTimeMinutes"), price=raw.get("costForTwo"),
                             area=raw.get("areaName"), rating=raw.get("avgRating"))
        if mapped:
            out.append(mapped)
    return out


def map_menu(payload: Any) -> tuple[dict, list[dict], bool]:
    """Returns (restaurant, items, has_more_pages)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("restaurant"), dict) \
            or not isinstance(payload.get("categories"), list):
        raise MappingError("get_restaurant_menu: expected 'restaurant' and 'categories'")
    r = payload["restaurant"]
    restaurant = _restaurant(r, open_value=r.get("isOpen"), minutes=r.get("deliveryTime"),
                             price=r.get("costForTwoMessage"), area=r.get("areaName"), rating=r.get("avgRating"))
    if restaurant is None:
        raise MappingError("get_restaurant_menu: the restaurant block is missing a required field")
    items, seen = [], set()
    for cat in payload["categories"]:
        if not isinstance(cat, dict) or not isinstance(cat.get("items"), list):
            continue
        title = _text(cat.get("title")) or ""
        for raw in cat["items"]:
            if not isinstance(raw, dict):
                continue
            iid, name, price = _ident(raw.get("id")), _text(raw.get("name")), _rupees(raw.get("price"))
            if iid is None or name is None or price is None or iid in seen or not isinstance(raw.get("isVeg"), bool):
                continue  # missing a field the agent needs, or the same dish repeated under another category
            seen.add(iid)
            items.append({"id": iid, "restaurant_id": restaurant["id"], "restaurant_name": restaurant["name"], "name": name, "price_inr": price,
                          "veg": raw["isVeg"], "category": title, "available": raw.get("inStock") in (1, True),
                          "has_options": bool(raw.get("hasVariants") or raw.get("hasAddons"))})
    return restaurant, items, payload.get("hasMore") is True


def map_addresses(payload: Any) -> tuple[list[dict], str | None]:
    """Returns (addresses, default address id). Phone numbers and anything else personal are not copied."""
    if not isinstance(payload, dict) or not isinstance(payload.get("addresses"), list):
        raise MappingError("get_addresses: expected an object with an 'addresses' list")
    out = []
    for raw in payload["addresses"]:
        aid = _ident(raw.get("id")) if isinstance(raw, dict) else None
        line = _text(raw.get("addressLine")) if isinstance(raw, dict) else None
        if aid and line:
            out.append({"id": aid, "category": _text(raw.get("addressCategory")) or "OTHER", "address_line": line})
    resolution = payload.get("resolution")
    default = _ident(resolution.get("defaultAddressId")) if isinstance(resolution, dict) else None
    return out, default if default in {a["id"] for a in out} else None
