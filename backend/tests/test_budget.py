import pytest
from mock_swiggy_mcp.data import MENUS, RESTAURANTS

from app.assistant.budget import build_plans, cheapest_possible

REST = {r["id"]: r for r in RESTAURANTS}
ALL = [i for items in MENUS.values() for i in items]
MAINS = [i for i in ALL if "biryani" in i["name"].lower()]
DRINKS = [i for i in ALL if i["category"] == "Beverage"]


def names(plan):
    return {l.name: l.quantity for l in plan.lines}


def test_two_people_500_picks_best_rated_restaurant_using_the_budget():
    plans = build_plans(MAINS, DRINKS, REST, people=2, budget=500)
    assert plans[0].restaurant_id == "r-007" and plans[0].subtotal_inr == 500
    assert names(plans[0]) == {"Hyderabadi Chicken Biryani": 2}
    assert {p.restaurant_id for p in plans} == {"r-007", "r-001"}
    assert all(p.subtotal_inr <= 500 for p in plans)


def test_variety_breaks_ties():
    plans = build_plans(MAINS, DRINKS, REST, people=2, budget=500)
    r1 = next(p for p in plans if p.restaurant_id == "r-001")
    assert names(r1) == {"Chicken Dum Biryani": 1, "Veg Biryani": 1} and r1.subtotal_inr == 500


def test_drinks_included_when_they_fit_and_flagged_when_not_offered():
    plans = build_plans(MAINS, DRINKS, REST, people=2, budget=500, want_drinks=True)
    top = plans[0]
    assert top.restaurant_id == "r-007" and top.drinks_ok
    assert names(top) == {"Hyderabadi Veg Biryani": 2, "Soft Drink (Cola)": 2} and top.subtotal_inr == 460
    other = next(p for p in plans if p.restaurant_id == "r-001")
    assert other.drinks_ok is False and all(l.role == "main" for l in other.lines)
    assert plans.index(top) < plans.index(other)  # plans that satisfy the request rank first


def test_drinks_dropped_when_budget_cannot_cover_them():
    plans = build_plans(MAINS, DRINKS, REST, people=2, budget=440, want_drinks=True)
    assert all(not p.drinks_ok for p in plans)  # 2 mains + 2 colas > 440 everywhere


def test_budget_never_exceeded():
    for people in (1, 2, 3, 4):
        for budget in range(150, 1200, 50):
            for want in (False, True):
                for p in build_plans(MAINS, DRINKS, REST, people, budget, want):
                    assert p.subtotal_inr <= budget
                    assert sum(l.quantity for l in p.lines if l.role == "main") == people


def test_three_people():
    plans = build_plans(MAINS, DRINKS, REST, people=3, budget=700)
    assert plans[0].subtotal_inr == 690 and sum(l.quantity for l in plans[0].lines) == 3


def test_impossible_budget_returns_nothing_and_reports_cheapest():
    assert build_plans(MAINS, DRINKS, REST, people=2, budget=300) == []
    assert cheapest_possible(MAINS, DRINKS, REST, people=2) == 380
    # with drinks: r-007 = 2*190 + 2*40 = 460, r-001 has no drinks so 2*220 = 440 -> cheapest is 440
    assert cheapest_possible(MAINS, DRINKS, REST, people=2, want_drinks=True) == 440


def test_closed_and_unavailable_are_excluded():
    rest = {**REST, "r-007": {**REST["r-007"], "is_open": False}}
    assert {p.restaurant_id for p in build_plans(MAINS, DRINKS, rest, 2, 600)} == {"r-001"}
    mains = [{**i, "available": False} if i["id"] == "m-001-02" else i for i in MAINS]
    plan = next(p for p in build_plans(mains, DRINKS, REST, 2, 600) if p.restaurant_id == "r-001")
    assert "Veg Biryani" not in names(plan)


def test_unknown_restaurant_items_are_ignored():
    assert build_plans([{"id": "x", "restaurant_id": "ghost", "name": "Ghost Biryani", "price_inr": 10,
                         "available": True}], [], REST, 1, 100) == []


def test_people_validation():
    with pytest.raises(ValueError):
        build_plans(MAINS, DRINKS, REST, people=0, budget=500)
    with pytest.raises(ValueError):
        build_plans(MAINS, DRINKS, REST, people=9, budget=500)


def test_top_n_and_empty_inputs():
    assert len(build_plans(MAINS, DRINKS, REST, 2, 500, top_n=1)) == 1
    assert build_plans([], [], REST, 2, 500) == [] and cheapest_possible([], [], REST, 2) is None
