async def test_health(api):
    r = await api.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


async def test_info_banner_and_capabilities(api):
    body = (await api.get("/api/platform/info")).json()
    assert body["synthetic"] is True and "synthetic" in body["banner"].lower()
    assert all(body["capabilities"].values())


async def test_restaurants_and_menu(api):
    r = await api.get("/api/restaurants", params={"query": "biryani"})
    assert r.status_code == 200 and r.json()["synthetic"] is True
    assert r.json()["data"][0]["id"] == "r-001"
    m = await api.get("/api/restaurants/r-001/menu")
    assert m.status_code == 200 and len(m.json()["data"]["items"]) == 5


async def test_404_for_unknown_restaurant(api):
    r = await api.get("/api/restaurants/nope")
    assert r.status_code == 404 and r.json()["detail"]["error"]["code"] == "not_found"


async def test_cart_endpoints(api):
    h = {"X-Session-Id": "t1"}
    r = await api.post("/api/cart/items", params={"item_id": "m-005-01", "quantity": 2}, headers=h)
    assert r.status_code == 200 and r.json()["data"]["subtotal_inr"] == 240
    r = await api.patch("/api/cart/items/m-005-01", params={"quantity": 3}, headers=h)
    assert r.json()["data"]["subtotal_inr"] == 360
    r = await api.delete("/api/cart/items/m-005-01", headers=h)
    assert r.json()["data"]["lines"] == []
    r = await api.post("/api/cart/items", params={"item_id": "m-002-05"}, headers=h)
    assert r.status_code == 409


async def test_orders(api):
    r = await api.get("/api/orders/ORD-DEMO-1002/status")
    assert r.json()["data"]["status"] == "OUT_FOR_DELIVERY"
