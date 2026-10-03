from app.main import app


async def test_chat_roundtrip_and_session_continuity(chat_api):
    r = await chat_api.post("/api/chat", json={"message": "add 2 masala dosa", "session_id": "u1"})
    assert r.status_code == 200
    b = r.json()
    assert b["session_id"] == "u1" and b["intent"] == "add_to_cart" and b["synthetic"] is True
    assert b["source"] == "mock" and b["tool_calls"][0]["name"] in {"search_menu", "add_to_cart"}
    r = await chat_api.post("/api/chat", json={"message": "make it 3", "session_id": "u1"})
    assert "Updated Masala Dosa to 3" in r.json()["reply"]


async def test_chat_cart_visible_through_phase1_api(chat_api):
    await chat_api.post("/api/chat", json={"message": "add 2 masala dosa", "session_id": "shared"})
    r = await chat_api.get("/api/cart", headers={"X-Session-Id": "shared"})
    assert r.json()["data"]["subtotal_inr"] == 180


async def test_chat_generates_session_id(chat_api):
    r = await chat_api.post("/api/chat", json={"message": "hi"})
    assert len(r.json()["session_id"]) == 32


async def test_chat_validation(chat_api):
    assert (await chat_api.post("/api/chat", json={"message": ""})).status_code == 422
    assert (await chat_api.post("/api/chat", json={"message": "x" * 501})).status_code == 422
    assert (await chat_api.post("/api/chat", json={"message": "hi", "session_id": "bad id!"})).status_code == 422
    assert (await chat_api.get("/api/chat/bad%20id/history")).status_code == 422


async def test_history_and_reset(chat_api):
    await chat_api.post("/api/chat", json={"message": "hi", "session_id": "h1"})
    h = (await chat_api.get("/api/chat/h1/history")).json()["history"]
    assert [t["role"] for t in h] == ["user", "assistant"]
    assert (await chat_api.delete("/api/chat/h1")).status_code == 204
    assert (await chat_api.get("/api/chat/h1/history")).json()["history"] == []


def test_new_routes_added_and_phase1_untouched():
    now = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}
    assert {("POST", "/api/chat"), ("GET", "/api/chat/{session_id}/history"),
            ("DELETE", "/api/chat/{session_id}")} <= now
