async def test_all_results_marked_synthetic(platform):
    r = await platform.search_restaurants()
    assert r.ok and r.synthetic and r.source == "mock" and len(r.data) == 7


async def test_search_filters(platform):
    r = await platform.search_restaurants(cuisine="Pizza")
    assert [x["id"] for x in r.data] == ["r-003"]
    r = await platform.search_restaurants(max_price_for_two_inr=300)
    assert {x["id"] for x in r.data} == {"r-002", "r-006"}
    r = await platform.search_restaurants(open_only=True)
    assert all(x["is_open"] for x in r.data)


async def test_menu_search_veg_and_budget(platform):
    r = await platform.search_menu(max_price_inr=100, veg_only=True)
    assert r.ok and r.data
    assert all(i["veg"] and i["price_inr"] <= 100 and i["available"] for i in r.data)


async def test_not_found(platform):
    r = await platform.get_restaurant_details("nope")
    assert not r.ok and r.error.code == "not_found"


async def test_cart_flow(platform):
    await platform.add_to_cart("m-002-01", 2, "s1")
    r = await platform.add_to_cart("m-002-04", 1, "s1")
    assert r.data["subtotal_inr"] == 90 * 2 + 40
    assert r.data["total_inr"] == r.data["subtotal_inr"] + r.data["delivery_fee_inr"]
    r = await platform.update_cart("m-002-01", 1, "s1")
    assert r.data["subtotal_inr"] == 130
    r = await platform.remove_from_cart("m-002-04", "s1")
    assert len(r.data["lines"]) == 1


async def test_cart_single_restaurant_and_unavailable(platform):
    await platform.add_to_cart("m-002-01", 1, "s2")
    r = await platform.add_to_cart("m-001-01", 1, "s2")
    assert r.error.code == "restaurant_conflict"
    r = await platform.add_to_cart("m-002-05", 1, "s3")
    assert r.error.code == "item_unavailable"


async def test_carts_isolated_by_session(platform):
    await platform.add_to_cart("m-002-01", 1, "a")
    r = await platform.get_cart("b")
    assert r.data["lines"] == []


async def test_orders(platform):
    assert (await platform.get_order_status("ORD-DEMO-1002")).data["status"] == "OUT_FOR_DELIVERY"
    assert (await platform.get_order_details("ORD-DEMO-1001")).data["total_inr"] == 210
    assert (await platform.get_order_status("x")).error.code == "not_found"


async def test_unreachable_mcp_reports_error():
    import httpx

    from app.platform.mcp_client import MockMCPClient
    from app.platform.mock_platform import MockSwiggyPlatform
    p = MockSwiggyPlatform(MockMCPClient("http://127.0.0.1:1", client=httpx.AsyncClient(timeout=1)))
    r = await p.search_restaurants()
    assert not r.ok and r.error.code == "mcp_unavailable"
