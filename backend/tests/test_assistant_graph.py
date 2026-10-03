"""Multi-turn conversations through the real graph + mock MCP (no network)."""
from app.assistant.session_store import InMemorySessionStore
from app.assistant.service import AssistantService
from app.assistant.nlu import RuleBasedNLU
from app.platform.real_platform import RealSwiggyPlatform

S = "t"


async def say(a, msg, sid=S):
    return await a.chat(msg, sid)


async def test_greet_and_help(assistant):
    assert (await say(assistant, "hi")).intent == "greet"
    r = await say(assistant, "what can you do?")
    assert r.intent == "help" and "can't place orders" in r.reply


async def test_search_restaurants_then_menu_by_ordinal(assistant):
    r = await say(assistant, "find pizza restaurants")
    assert r.intent == "search_restaurants" and "Test Pizza Lab" in r.reply
    assert r.synthetic is True and r.source == "mock"
    r = await say(assistant, "show the menu of the first one")
    assert r.intent == "show_menu" and "Margherita Pizza" in r.reply and "₹260" in r.reply
    assert [c.name for c in r.tool_calls] == ["get_menu"]


async def test_menu_search_budget_and_veg(assistant):
    r = await say(assistant, "show me veg items under 100")
    assert r.intent == "search_menu"
    assert all(i["veg"] and i["price_inr"] <= 100 for i in r.cards["items"]) and r.cards["items"]
    assert "Pepperoni" not in r.reply and "Chicken" not in r.reply


async def test_non_veg_filter(assistant):
    r = await say(assistant, "show non veg items")
    assert r.cards["items"] and all(not i["veg"] for i in r.cards["items"])


async def test_add_by_name_and_view_cart(assistant):
    r = await say(assistant, "add 2 masala dosa to my cart")
    assert r.intent == "add_to_cart" and "Added 2 × Masala Dosa" in r.reply
    assert r.cards["cart"]["subtotal_inr"] == 180
    r = await say(assistant, "what's in my cart")
    assert r.intent == "view_cart" and "2 × Masala Dosa" in r.reply and "₹210" in r.reply  # 180 + 30 fee


async def test_add_by_ordinal_after_menu(assistant):
    await say(assistant, "find dosa restaurants")
    await say(assistant, "menu of the first one")
    r = await say(assistant, "add the second one")
    assert "Added 1 × Idli (3 pc)" in r.reply


async def test_ambiguous_dish_asks_then_resolves(assistant):
    r = await say(assistant, "add 2 biryani")
    assert "Which one" in r.reply and "Chicken Dum Biryani" in r.reply and "Veg Biryani" in r.reply
    r = await say(assistant, "2")
    assert "Added 2 × Veg Biryani" in r.reply


async def test_invalid_choice_keeps_pending(assistant):
    await say(assistant, "add biryani")
    r = await say(assistant, "7")
    assert r.intent == "invalid_choice" and "between 1 and 5" in r.reply
    r = await say(assistant, "1")
    assert "Added 1 × Chicken Dum Biryani" in r.reply


async def test_select_item_then_confirm_yes_and_no(assistant):
    await say(assistant, "show veg items under 100")
    r = await say(assistant, "the first one")
    assert "Say 'yes' or 'no'" in r.reply
    assert "Added" in (await say(assistant, "yes")).reply
    r = await say(assistant, "the second one")
    r = await say(assistant, "no")
    assert r.reply == "Okay, no problem."
    assert len((await say(assistant, "show cart")).cards["cart"]["lines"]) == 1


async def test_update_and_remove(assistant):
    await say(assistant, "add 2 masala dosa")
    r = await say(assistant, "make it 3")
    assert "Updated Masala Dosa to 3" in r.reply and r.cards["cart"]["subtotal_inr"] == 270
    await say(assistant, "add 1 filter coffee")
    r = await say(assistant, "change idli to 2")
    assert r.reply.startswith("I couldn't tell which cart item") and r.tool_calls[-1].name == "get_cart"
    r = await say(assistant, "remove the coffee")
    assert "Removed Filter Coffee" in r.reply and len(r.cards["cart"]["lines"]) == 1
    r = await say(assistant, "set dosa to 0")
    assert "Removed Masala Dosa" in r.reply and "empty" in r.reply


async def test_cart_conflict_is_explained(assistant):
    await say(assistant, "add masala dosa")
    r = await say(assistant, "add 1 veg burger")
    assert "another restaurant" in r.reply and r.cards == {}


async def test_unavailable_item_not_addable(assistant):
    r = await say(assistant, "add rava kesari")
    assert "couldn't find" in r.reply.lower()  # unavailable items are hidden from search


async def test_quantity_limits(assistant):
    r = await say(assistant, "add 50 masala dosa")
    assert "between 1 and 20" in r.reply and (await say(assistant, "show cart")).cards["cart"]["lines"] == []


async def test_order_status_and_details(assistant):
    r = await say(assistant, "where is my order ORD-DEMO-1002")
    assert r.reply == "Order ORD-DEMO-1002 is out for delivery."
    r = await say(assistant, "details of order ORD-DEMO-1001")
    assert "2 × Masala Dosa" in r.reply and "₹210" in r.reply
    assert "ID" in (await say(assistant, "track my order")).reply
    assert "couldn't find" in (await say(assistant, "status of order ORD-NOPE-1")).reply


async def test_unsupported_actions_are_honest(assistant):
    for msg in ["checkout", "place my order", "cancel my order", "pay now"]:
        r = await say(assistant, msg)
        assert r.intent == "unsupported_action" and "can't place or cancel" in r.reply
        assert r.tool_calls == []


async def test_unknown_input(assistant):
    assert (await say(assistant, "asdf qwerty zxcv lkj poiu mnb")).intent == "unknown"


async def test_sessions_are_isolated(assistant):
    await say(assistant, "add masala dosa", "alice")
    assert (await say(assistant, "show cart", "bob")).cards["cart"]["lines"] == []
    assert (await say(assistant, "show cart", "alice")).cards["cart"]["lines"]


async def test_history_recorded(assistant):
    await say(assistant, "hi")
    h = await assistant.history(S)
    assert [t.role for t in h] == ["user", "assistant"] and h[0].text == "hi"


async def test_new_session_id_generated(assistant):
    r = await assistant.chat("hi")
    assert len(r.session_id) == 32


async def test_real_mode_never_fabricates():
    a = AssistantService(RealSwiggyPlatform(), RuleBasedNLU(), InMemorySessionStore())
    for msg in ["find pizza restaurants", "show veg items under 100", "add masala dosa", "show cart",
                "status of order ORD-DEMO-1002"]:
        r = await a.chat(msg, "x")
        assert r.synthetic is False and r.source == "swiggy"
        assert "Sorry" in r.reply and "Stage 2" in r.reply
        assert r.cards == {} and all(c.error_code == "unsupported_capability" for c in r.tool_calls)
