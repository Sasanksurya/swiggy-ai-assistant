import pytest

from app.assistant.nlu import RuleBasedNLU

nlu = RuleBasedNLU()


async def p(msg, pending=False):
    return await nlu.parse(msg, has_pending=pending)


@pytest.mark.parametrize("msg,intent", [
    ("hi", "greet"), ("Hello there", "greet"), ("what can you do?", "help"),
    ("find pizza restaurants", "search_restaurants"), ("any good places for biryani", "search_restaurants"),
    ("show me veg items under 100", "search_menu"), ("something cheap", "search_menu"),
    ("show the menu of the first one", "show_menu"), ("menu", "show_menu"),
    ("add 2 masala dosa to my cart", "add_to_cart"), ("I want 3 idli", "add_to_cart"),
    ("order a veg burger", "add_to_cart"),
    ("what's in my cart", "view_cart"), ("show cart", "view_cart"),
    ("remove the dosa", "remove_from_cart"), ("delete idli from cart", "remove_from_cart"),
    ("make it 3", "update_cart"), ("change idli to 4", "update_cart"),
    ("where is my order ORD-DEMO-1002", "order_status"), ("track order", "order_status"),
    ("details of order ORD-DEMO-1001", "order_details"),
    ("checkout", "place_order"), ("place my order", "place_order"), ("confirm my order", "place_order"),
    ("pay now", "place_order"), ("cancel my order", "cancel_order"), ("I want a refund", "cancel_order"),
    ("what payment options do you have", "unsupported_action"),
    ("yes", "affirm"), ("no", "deny"), ("the second one", "select"), ("2", "select"),
    ("asdf qwerty zxcv lkj poiu mnb", "unknown"),
])
async def test_intent(msg, intent):
    assert (await p(msg)).intent == intent


async def test_entities_budget_veg_query():
    r = await p("show me veg biryani under ₹250")
    assert (r.intent, r.max_price, r.veg, r.query) == ("search_menu", 250, True, "biryani")


async def test_budget_variants():
    assert (await p("cheap dosa within 100 rupees")).max_price == 100
    assert (await p("pizza budget of 300")).max_price == 300
    assert (await p("rs 150 or less dosa")).max_price == 150


async def test_non_veg_flag():
    assert (await p("non veg items")).veg is False
    assert (await p("veg items")).veg is True


async def test_quantity_and_name_extraction():
    r = await p("add 2 masala dosa to my cart")
    assert (r.quantity, r.query) == (2, "masala dosa")
    r = await p("I want three idli")
    assert (r.quantity, r.query) == (3, "idli")


async def test_ordinals_do_not_become_quantity():
    r = await p("add the 2nd one")
    assert r.intent == "add_to_cart" and r.ref_index == 2 and r.quantity is None
    r = await p("add the last one")
    assert r.ref_index == -1


async def test_order_id_not_quantity_or_query():
    r = await p("status of order ORD-DEMO-1002")
    assert r.order_id == "ORD-DEMO-1002" and r.quantity is None and r.query is None


async def test_unknown_has_low_confidence():
    assert (await p("asdf qwerty zxcv lkj poiu mnb")).confidence < 0.5


# ---------- Phase 3: Sarah persona, people, budget phrasing, drinks, meal planning ----------

async def test_users_dictated_sentence():
    r = await p("Hey Sarah, I'm looking for biryani at a range of 500 for two combos")
    assert (r.intent, r.query, r.max_price, r.people) == ("plan_meal", "biryani", 500, 2)


async def test_budget_and_people_sentence_with_drinks():
    r = await p("Hey Sarah, my budget is around 500 and two people are looking for biryani, add two cokes also")
    assert r.intent == "plan_meal" and (r.max_price, r.people, r.query) == (500, 2, "biryani")
    assert r.wants_drinks and r.drink_query == "cola"


async def test_wake_phrase_alone_is_a_greeting():
    assert (await p("Hey Sarah")).intent == "greet"
    assert (await p("sarah!")).intent == "greet"


async def test_wake_phrase_is_stripped_from_any_request():
    r = await p("hey sarah show me veg items under 100")
    assert (r.intent, r.max_price, r.veg) == ("search_menu", 100, True) and "sarah" not in (r.query or "")


async def test_custom_assistant_name():
    from app.assistant.nlu import RuleBasedNLU
    r = await RuleBasedNLU("Maya").parse("hey maya find pizza restaurants")
    assert r.intent == "search_restaurants" and "maya" not in (r.query or "")


async def test_budget_phrasings():
    for msg in ["biryani for two budget 500", "biryani for two around 500", "biryani for two ₹500 budget",
                "biryani for 2 people in the range of 500", "500 budget biryani for two people"]:
        r = await p(msg)
        assert (r.intent, r.max_price, r.people) == ("plan_meal", 500, 2), msg


async def test_people_phrasings():
    assert (await p("biryani for 3 people under 600")).people == 3
    assert (await p("biryani for four under 800")).people == 4
    assert (await p("biryani for one person under 300")).people == 1


async def test_partial_meal_requests():
    r = await p("looking for biryani for two people")
    assert (r.intent, r.people, r.max_price) == ("plan_meal", 2, None)
    r = await p("two people")
    assert r.people == 2


async def test_small_numbers_are_not_budgets():
    r = await p("add 2 masala dosa for about 2 people")
    assert r.max_price is None


async def test_drinks_detection():
    assert (await p("biryani for two under 500 with drinks")).wants_drinks
    r = await p("biryani for two under 500 with a coke")
    assert r.drink_query == "cola"
    assert not (await p("biryani for two under 500")).wants_drinks


async def test_use_plan_intent():
    r = await p("use option 2")
    assert (r.intent, r.ref_index) == ("use_plan", 2)
    assert (await p("switch to the second plan")).intent == "use_plan"


async def test_phase2_behaviour_unchanged_by_new_rules():
    assert (await p("show me veg items under 100")).intent == "search_menu"
    assert (await p("add 2 masala dosa")).intent == "add_to_cart"
    assert (await p("any good places for biryani")).intent == "search_restaurants"


async def test_checkout_wording_never_swallows_normal_requests():
    assert (await p("add 2 masala dosa to my order")).intent == "add_to_cart"
    assert (await p("show me veg items under 100")).intent == "search_menu"
    assert (await p("where is my order ORD-DEMO-1002")).intent == "order_status"
    assert (await p("confirm")).intent == "affirm"  # a bare "confirm" answers a question, it does not start checkout


async def test_natural_ways_to_confirm_but_never_a_request_that_merely_starts_with_yes():
    for ok in ["yes", "Yes!", "yes please", "yes, place it", "yeah", "go ahead", "confirm", "ok please"]:
        assert (await p(ok)).intent == "affirm", ok
    assert (await p("yes add 2 masala dosa")).intent == "add_to_cart"
    assert (await p("yes show me the menu")).intent != "affirm"
