"""Platform-level checkout: synthetic addresses and SIMULATED order placement in the mock."""
import pytest


async def test_addresses_are_synthetic_and_have_no_phone_numbers(platform):
    r = await platform.get_addresses()
    assert r.ok and r.synthetic and len(r.data) == 2
    for a in r.data:
        assert set(a) == {"id", "category", "address_line"} and "(Synthetic)" in a["address_line"]


async def test_place_order_creates_a_simulated_order_and_empties_the_cart(platform):
    await platform.add_to_cart("m-002-01", 2, "s1")  # 2 x Masala Dosa = 180 + 30 delivery
    r = await platform.place_order("addr-001", "COD", "s1")
    assert r.ok and r.synthetic
    o = r.data
    assert o["order_id"] == "ORD-SIM-0001" and o["status"] == "CONFIRMED" and o["simulated"] is True
    assert o["total_inr"] == 210 and o["payment_method"] == "COD"
    assert o["items"] == [{"item_id": "m-002-01", "name": "Masala Dosa", "quantity": 2}]
    assert (await platform.get_cart("s1")).data["lines"] == []


async def test_placed_orders_can_be_tracked_like_any_order(platform):
    await platform.add_to_cart("m-002-01", 1, "s1")
    oid = (await platform.place_order("addr-002", "COD", "s1")).data["order_id"]
    assert (await platform.get_order_status(oid)).data["status"] == "CONFIRMED"
    assert (await platform.get_order_details(oid)).data["delivery_address"].startswith("Demo Office Park")
    assert (await platform.get_order_status("ORD-DEMO-1002")).data["status"] == "OUT_FOR_DELIVERY"  # unchanged


async def test_order_numbers_increase(platform):
    for expected in ("ORD-SIM-0001", "ORD-SIM-0002"):
        await platform.add_to_cart("m-002-01", 1, "s1")
        assert (await platform.place_order("addr-001", "COD", "s1")).data["order_id"] == expected


@pytest.mark.parametrize("kwargs,code", [
    ({"address_id": "nope"}, "not_found"),
    ({"address_id": "addr-001", "payment_method": "UPI"}, "invalid_argument"),
])
async def test_invalid_orders_are_rejected_and_keep_the_cart(platform, kwargs, code):
    await platform.add_to_cart("m-002-01", 1, "s1")
    r = await platform.place_order(session_id="s1", **kwargs)
    assert not r.ok and r.error.code == code
    assert len((await platform.get_cart("s1")).data["lines"]) == 1  # nothing was lost


async def test_empty_cart_cannot_be_ordered(platform):
    r = await platform.place_order("addr-001", "COD", "empty")
    assert not r.ok and r.error.code == "empty_cart"


async def test_the_cart_cap_is_enforced_like_the_real_platform(platform):
    await platform.add_to_cart("m-003-02", 3, "big")  # 3 x Pepperoni 340 = 1020 + 30
    r = await platform.place_order("addr-001", "COD", "big")
    assert not r.ok and r.error.code == "cart_cap_exceeded" and "1000" in r.error.message
    assert (await platform.get_cart("big")).data["lines"]


async def test_orders_are_isolated_per_session(platform):
    await platform.add_to_cart("m-002-01", 1, "a")
    await platform.add_to_cart("m-002-02", 1, "b")
    await platform.place_order("addr-001", "COD", "a")
    assert (await platform.get_cart("b")).data["lines"]


async def test_checkout_endpoints_exist_only_as_capabilities(platform):
    caps = platform.capabilities()
    assert caps["get_addresses"] and caps["place_order"]
