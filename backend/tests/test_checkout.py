"""Sarah's checkout: address -> full summary -> explicit yes -> order. Includes the ways a 'yes' must NOT order."""
from app.assistant.nlu import RuleBasedNLU
from app.assistant.service import AssistantService
from app.assistant.session_store import InMemorySessionStore
from app.platform.base import PlatformError, PlatformResult
from app.platform.mock_platform import MockSwiggyPlatform
from app.platform.real_platform import RealSwiggyPlatform

S = "co"


async def say(a, msg, sid=S):
    return await a.chat(msg, sid)


def placed(r):
    return any(t.name == "place_order" for t in r.tool_calls)


async def lines(a, sid=S):
    """Read the cart straight from the platform, so checking it never disturbs the conversation."""
    return (await a._platform.get_cart(sid)).data["lines"]


def service(platform, **kw):
    return AssistantService(platform, RuleBasedNLU(), InMemorySessionStore(), **kw)


class OneAddress(MockSwiggyPlatform):
    async def get_addresses(self):
        return PlatformResult(ok=True, source="mock", synthetic=True,
                              data=[{"id": "addr-001", "category": "Home", "address_line": "Only Home (Synthetic)"}])


class NoAddress(MockSwiggyPlatform):
    async def get_addresses(self):
        return PlatformResult(ok=True, source="mock", synthetic=True, data=[])


class FlakyOrder(MockSwiggyPlatform):
    """The connection drops while the order is being placed."""
    async def place_order(self, *a, **k):
        return PlatformResult(ok=False, source="mock", synthetic=True,
                              error=PlatformError(code="mcp_unavailable", message="timeout"))


async def test_empty_cart_is_not_checked_out(assistant):
    r = await say(assistant, "checkout")
    assert r.intent == "place_order" and "cart is empty" in r.reply and not placed(r)


async def test_full_flow_with_address_choice_summary_and_explicit_yes(assistant):
    await say(assistant, "add 2 masala dosa")
    r = await say(assistant, "checkout")
    assert "Where should I deliver this?" in r.reply and "Home:" in r.reply and "Work:" in r.reply
    assert not placed(r)

    r = await say(assistant, "2")
    assert "Demo Office Park" in r.reply and "2 × Masala Dosa" in r.reply and "= ₹210" in r.reply
    assert "cash on delivery" in r.reply
    assert "Do you want to proceed with placing this order to this address?" in r.reply
    assert r.cards["checkout"]["requires_confirmation"] is True and r.cards["checkout"]["total_inr"] == 210
    assert not placed(r) and len(await lines(assistant)) == 1  # nothing ordered yet

    r = await say(assistant, "yes")
    assert placed(r) and r.intent == "affirm"
    assert "Done! Order ORD-SIM-0001 is confirmed" in r.reply and "Total ₹210" in r.reply
    assert "simulated demo order" in r.reply and "Nothing was ordered or charged" in r.reply
    assert r.cards["order"]["order_id"] == "ORD-SIM-0001" and r.cards["cart"]["lines"] == []
    assert await lines(assistant) == []

    r = await say(assistant, "where is my order ORD-SIM-0001")
    assert r.reply == "Order ORD-SIM-0001 is confirmed."


async def test_address_can_be_chosen_by_name(assistant):
    await say(assistant, "add masala dosa")
    await say(assistant, "place my order")
    r = await say(assistant, "work")
    assert "Delivering to: Demo Office Park" in r.reply


async def test_address_is_remembered_for_the_next_order(assistant):
    await say(assistant, "add masala dosa")
    await say(assistant, "checkout")
    await say(assistant, "1")
    await say(assistant, "yes")
    await say(assistant, "add 1 idli")
    r = await say(assistant, "checkout")
    assert "Where should I deliver" not in r.reply and "Delivering to: Flat 101" in r.reply
    assert not any(t.name == "get_addresses" for t in r.tool_calls)


async def test_one_saved_address_is_used_but_still_shown_for_confirmation(platform):
    a = service(OneAddress(platform._c))
    await say(a, "add masala dosa")
    r = await say(a, "checkout")
    assert "Delivering to: Only Home" in r.reply and "Do you want to proceed" in r.reply and not placed(r)


async def test_no_saved_address(platform):
    a = service(NoAddress(platform._c))
    await say(a, "add masala dosa")
    r = await say(a, "checkout")
    assert "don't have a saved delivery address" in r.reply and not placed(r)


async def test_no_cancels_and_a_later_yes_orders_nothing(assistant):
    await say(assistant, "add masala dosa")
    await say(assistant, "checkout")
    await say(assistant, "1")
    r = await say(assistant, "no")
    assert "won't place the order" in r.reply and "cart is unchanged" in r.reply
    r = await say(assistant, "yes")
    assert not placed(r) and r.reply.startswith("There's nothing waiting for your confirmation")
    assert len(await lines(assistant)) == 1


async def test_moving_on_invalidates_the_summary(assistant):
    await say(assistant, "add masala dosa")
    await say(assistant, "checkout")
    await say(assistant, "1")
    await say(assistant, "show cart")  # the user went and did something else
    r = await say(assistant, "yes")
    assert not placed(r) and len(await lines(assistant)) == 1


async def test_a_yes_is_single_use(assistant):
    await say(assistant, "add masala dosa")
    await say(assistant, "checkout")
    await say(assistant, "1")
    assert placed(await say(assistant, "yes"))
    r = await say(assistant, "yes")
    assert not placed(r)


async def test_natural_confirmations_work(assistant):
    for i, phrase in enumerate(["yes please", "confirm", "go ahead"]):
        sid = f"nat{i}"
        await say(assistant, "add masala dosa", sid)
        await say(assistant, "checkout", sid)
        await say(assistant, "1", sid)
        assert placed(await say(assistant, phrase, sid)), phrase


async def test_asking_to_place_the_order_again_reshows_the_summary_instead_of_ordering(assistant):
    await say(assistant, "add masala dosa")
    await say(assistant, "checkout")
    await say(assistant, "1")
    r = await say(assistant, "place my order")
    assert not placed(r) and "Do you want to proceed" in r.reply


async def test_cart_changed_behind_the_summary_forces_a_new_confirmation(assistant):
    await say(assistant, "add masala dosa")
    await say(assistant, "checkout")
    await say(assistant, "1")
    await assistant._platform.add_to_cart("m-002-04", 1, S)  # e.g. changed through the REST API meanwhile
    r = await say(assistant, "yes")
    assert not placed(r) and "cart changed" in r.reply and "Filter Coffee" in r.reply
    r = await say(assistant, "yes")
    assert placed(r) and "Total ₹160" in r.reply  # 90 + 40 + 30 delivery, the amount the user last saw


async def test_the_order_cap_is_explained_and_nothing_is_lost(assistant):
    await say(assistant, "add 3 pepperoni pizza")
    await say(assistant, "checkout")
    await say(assistant, "1")
    r = await say(assistant, "yes")
    assert "limited to ₹1000" in r.reply and "Remove something" in r.reply
    assert len(await lines(assistant)) == 1


async def test_a_dropped_connection_never_claims_success(platform):
    a = service(FlakyOrder(platform._c))
    await say(a, "add masala dosa")
    await say(a, "checkout")
    await say(a, "1")
    r = await say(a, "yes")
    assert "couldn't confirm whether your order went through" in r.reply and "don't order twice" in r.reply
    assert "Done" not in r.reply and len(await lines(a)) == 1


async def test_orders_can_be_switched_off(platform):
    a = service(platform, allow_orders=False)
    r = await say(a, "checkout")
    assert "switched off" in r.reply and r.tool_calls == []
    assert "I can't place or cancel orders." in (await say(a, "what can you do?")).reply


async def test_real_platform_without_ordering_never_pretends():
    a = service(RealSwiggyPlatform())
    r = await say(a, "checkout")
    assert "Sorry" in r.reply and "Stage 2" in r.reply and not placed(r)
    assert r.synthetic is False and r.cards == {}


async def test_cancellation_is_redirected_to_swiggy_customer_care(assistant):
    r = await say(assistant, "cancel my order")
    assert r.intent == "cancel_order" and "080-67466729" in r.reply and "no real orders" in r.reply
    assert r.tool_calls == []


async def test_other_payment_talk_is_declined_honestly(assistant):
    r = await say(assistant, "what payment options do you have")
    assert r.intent == "unsupported_action" and "can't help with payments" in r.reply


async def test_sessions_checkout_independently(assistant):
    await say(assistant, "add masala dosa", "alice")
    await say(assistant, "checkout", "alice")
    await say(assistant, "1", "alice")
    r = await say(assistant, "yes", "bob")  # bob never saw a summary
    assert not placed(r)
    assert len(await lines(assistant, "alice")) == 1
