"""Budget engine: given dishes returned by the platform, pick the best meal per restaurant.

Pure functions, no I/O. Inputs are tool results (dicts); outputs are Plans built only from those
items and their prices. Nothing is estimated except what the caller passes in (e.g. `budget`).
"""
from __future__ import annotations

from itertools import combinations_with_replacement
from typing import Literal

from pydantic import BaseModel

MAX_PEOPLE = 8
_MAX_MAINS_PER_RESTAURANT = 8  # keeps the combination search tiny and fast


class PlanLine(BaseModel):
    item_id: str
    name: str
    price_inr: int
    quantity: int
    role: Literal["main", "drink"]


class Plan(BaseModel):
    restaurant_id: str
    restaurant_name: str
    rating: float | None = None
    delivery_time_min: int | None = None
    lines: list[PlanLine]
    subtotal_inr: int
    drinks_ok: bool = True  # False => drinks were requested but could not be included


def _by_restaurant(items: list[dict], restaurants: dict[str, dict]) -> dict[str, list[dict]]:
    out: dict[str, dict[str, dict]] = {}
    for i in items:
        r = restaurants.get(i["restaurant_id"])
        if r and r.get("is_open", True) and i.get("available", True):
            out.setdefault(i["restaurant_id"], {})[i["id"]] = i
    return {rid: sorted(d.values(), key=lambda x: (x["price_inr"], x["name"])) for rid, d in out.items()}


def _lines(combo: tuple[dict, ...], drink: dict | None, people: int) -> list[PlanLine]:
    counts: dict[str, list] = {}
    for it in combo:
        counts.setdefault(it["id"], [it, 0])[1] += 1
    lines = [PlanLine(item_id=i["id"], name=i["name"], price_inr=i["price_inr"], quantity=q, role="main")
             for i, q in counts.values()]
    if drink:
        lines.append(PlanLine(item_id=drink["id"], name=drink["name"], price_inr=drink["price_inr"],
                              quantity=people, role="drink"))
    return lines


def _best_combo(mains: list[dict], people: int, limit: int) -> tuple[dict, ...] | None:
    """Highest total within `limit`; ties broken by more distinct dishes (variety)."""
    best, best_key = None, None
    for combo in combinations_with_replacement(mains[:_MAX_MAINS_PER_RESTAURANT], people):
        total = sum(i["price_inr"] for i in combo)
        if total > limit:
            continue
        key = (total, len({i["id"] for i in combo}))
        if best_key is None or key > best_key:
            best, best_key = combo, key
    return best


def build_plans(mains: list[dict], drinks: list[dict], restaurants: dict[str, dict], people: int,
                budget: int, want_drinks: bool = False, top_n: int = 3) -> list[Plan]:
    """One best plan per open restaurant that fits `budget` (items only), ranked best-first.

    Ranking: plans that include requested drinks first, then higher rating, faster delivery,
    higher use of the budget.
    """
    if not 1 <= people <= MAX_PEOPLE:
        raise ValueError(f"people must be between 1 and {MAX_PEOPLE}")
    m_by, d_by = _by_restaurant(mains, restaurants), _by_restaurant(drinks, restaurants)
    plans: list[Plan] = []
    for rid, ms in m_by.items():
        r = restaurants[rid]
        drink = d_by.get(rid, [None])[0] if want_drinks else None
        combo, used_drink = None, None
        if drink:
            combo = _best_combo(ms, people, budget - drink["price_inr"] * people)
            used_drink = drink if combo else None
        if not combo:
            combo = _best_combo(ms, people, budget)
        if not combo:
            continue
        lines = _lines(combo, used_drink, people)
        plans.append(Plan(
            restaurant_id=rid, restaurant_name=r["name"], rating=r.get("rating"),
            delivery_time_min=r.get("delivery_time_min"), lines=lines,
            subtotal_inr=sum(l.price_inr * l.quantity for l in lines),
            drinks_ok=(not want_drinks) or used_drink is not None))
    plans.sort(key=lambda p: (not p.drinks_ok, -(p.rating or 0), p.delivery_time_min or 999, -p.subtotal_inr))
    return plans[:top_n]


def cheapest_possible(mains: list[dict], drinks: list[dict], restaurants: dict[str, dict], people: int,
                      want_drinks: bool = False) -> int | None:
    """Lowest item total that could serve `people` (used to explain an impossible budget)."""
    m_by, d_by = _by_restaurant(mains, restaurants), _by_restaurant(drinks, restaurants)
    totals = []
    for rid, ms in m_by.items():
        total = ms[0]["price_inr"] * people
        if want_drinks and d_by.get(rid):
            total += d_by[rid][0]["price_inr"] * people
        totals.append(total)
    return min(totals) if totals else None
