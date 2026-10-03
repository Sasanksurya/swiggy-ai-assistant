"""Sarah's meal planning: people + budget + dish -> best restaurant -> cart, through the real graph."""
from app.assistant.nlu import RuleBasedNLU
from app.assistant.service import AssistantService
from app.assistant.session_store import InMemorySessionStore
from app.platform.real_platform import RealSwiggyPlatform

S = "m"


async def say(a, msg, sid=S):
    return await a.chat(msg, sid)


async def cart(a, sid=S):
    return (await a.chat("show cart", sid)).cards["cart"]


def lines(c):
    return {l["name"]: l["quantity"] for l in c["lines"]}


async def test_users_scenario_biryani_for_two_around_500(assistant):
    r = await say(assistant, "Hey Sarah, I'm looking for biryani at a range of 500 for two combos")
    assert r.intent == "plan_meal" and r.assistant_name == "Sarah"
    c = await cart(assistant)
    assert c["total_inr"] <= 500  # including the delivery fee reported by the platform
    assert c["restaurant_id"] == "r-007" and sum(l["quantity"] for l in c["lines"]) == 2
    assert "under your budget" in r.reply and "I've added it to your cart" in r.reply


async def test_delivery_fee_triggers_one_replan(assistant):
    r = await say(assistant, "biryani for two budget 500")
    # first pick (2 x Hyderabadi Chicken = 500) + 30 delivery > 500 -> adjusted using the platform's fee
    assert "delivery fee would have gone over your budget" in r.reply
    names = [t.name for t in r.tool_calls]
    assert names.count("remove_from_cart") >= 1 and names.count("add_to_cart") >= 3
    assert lines(await cart(assistant)) == {"Hyderabadi Chicken Biryani": 1, "Hyderabadi Veg Biryani": 1}


async def test_with_drinks_cokes(assistant):
    r = await say(assistant, "Hey Sarah, my budget is around 500 and two people want biryani, add two cokes also")
    assert lines(await cart(assistant)) == {"Hyderabadi Veg Biryani": 2, "Soft Drink (Cola)": 2}
    assert "₹10 under your budget" in r.reply  # 380 + 80 + 30 fee = 490


async def test_drinks_that_do_not_fit_are_reported(assistant):
    r = await say(assistant, "biryani for two under 440 with drinks")
    assert "couldn't fit the drinks" in r.reply


async def test_missing_budget_then_answer(assistant):
    r = await say(assistant, "Hey Sarah, I want biryani for two people")
    assert r.intent == "plan_meal" and "budget" in r.reply.lower() and r.tool_calls == []
    r = await say(assistant, "500")
    assert r.intent == "plan_meal" and "added it to your cart" in r.reply
    assert (await cart(assistant))["total_inr"] <= 500


async def test_missing_people_then_budget(assistant):
    r = await say(assistant, "I'm looking for biryani")  # plain search, not a plan
    assert r.intent == "search_menu"
    r = await say(assistant, "plan biryani under 500")
    assert "How many people" in r.reply
    r = await say(assistant, "2")
    assert "added it to your cart" in r.reply
    assert (await cart(assistant))["lines"]


async def test_missing_dish_then_answer(assistant):
    r = await say(assistant, "budget 500 for two people")
    assert "What would you like to eat" in r.reply
    r = await say(assistant, "biryani")
    assert "added it to your cart" in r.reply


async def test_moving_on_clears_the_half_finished_request(assistant):
    await say(assistant, "I want biryani for two people")
    await say(assistant, "show cart")  # user moved on
    r = await say(assistant, "500")
    assert r.intent == "select"  # a bare number no longer means "budget"


async def test_impossible_budget_explains_cheapest(assistant):
    r = await say(assistant, "biryani for two under 300")
    assert "couldn't fit" in r.reply and "₹380" in r.reply
    assert (await cart(assistant))["lines"] == []


async def test_veg_only(assistant):
    await say(assistant, "veg biryani for two under 500")
    assert set(lines(await cart(assistant))) <= {"Veg Biryani", "Hyderabadi Veg Biryani"}


async def test_unknown_dish(assistant):
    r = await say(assistant, "sushi for two under 500")
    assert "couldn't find any open restaurant serving sushi" in r.reply


async def test_group_size_limit(assistant):
    r = await say(assistant, "biryani for 12 people under 5000")
    assert "1 to 8 people" in r.reply
    assert r.tool_calls == []


async def test_existing_cart_is_never_changed_without_consent(assistant):
    await say(assistant, "add 1 masala dosa")
    r = await say(assistant, "biryani for two under 500")
    assert "haven't changed it" in r.reply
    assert not any(t.name in {"add_to_cart", "remove_from_cart"} for t in r.tool_calls)
    assert lines(await cart(assistant)) == {"Masala Dosa": 1}
    r = await say(assistant, "use option 1")  # explicit command -> replace
    assert "Switched your cart" in r.reply and "Masala Dosa" not in lines(await cart(assistant))


async def test_switch_to_another_option(assistant):
    await say(assistant, "biryani for two under 500")
    r = await say(assistant, "use option 2")
    assert "Switched your cart" in r.reply
    c = await cart(assistant)
    assert c["restaurant_id"] == "r-001" and c["total_inr"] <= 500
    assert "between 1 and" in (await say(assistant, "use option 9")).reply


async def test_use_plan_without_plans(assistant):
    assert "don't have any meal options" in (await say(assistant, "use option 1")).reply


async def test_budget_is_respected_across_many_requests(assistant):
    for i, budget in enumerate(range(450, 1000, 50)):
        sid = f"b{i}"
        r = await say(assistant, f"biryani for two under {budget}", sid)
        c = await cart(assistant, sid)
        if c["lines"]:
            assert c["total_inr"] <= budget or "over your budget" in r.reply, (budget, r.reply)


async def test_sarah_persona(assistant):
    r = await say(assistant, "Hey Sarah")
    assert r.intent == "greet" and "Sarah" in r.reply and "biryani for two under 500" in r.reply
    assert "Sarah" in (await say(assistant, "what can you do?")).reply


async def test_real_mode_plans_nothing():
    a = AssistantService(RealSwiggyPlatform(), RuleBasedNLU(), InMemorySessionStore())
    r = await a.chat("biryani for two under 500", "x")
    assert r.synthetic is False and "Sorry" in r.reply and "Stage 2" in r.reply and r.cards == {}


async def test_reply_is_speakable_each_dish_named_once(assistant):
    r = await say(assistant, "biryani for two under 500 with cokes", "v")
    for name in ("Hyderabadi Veg Biryani", "Soft Drink (Cola)"):
        assert r.reply.count(name) == 1, r.reply
    assert "(items, before delivery)" in r.reply
