import httpx
import pytest

from app.api.swiggy_auth import get_oauth
from app.config import Settings, get_settings
from app.main import app as backend_app


@pytest.fixture
async def swiggy_api(oauth):
    backend_app.dependency_overrides[get_oauth] = lambda: oauth
    backend_app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=backend_app), base_url="http://test") as c:
        yield c
    backend_app.dependency_overrides.clear()


async def test_status_before_connecting(swiggy_api):
    body = (await swiggy_api.get("/api/swiggy/status")).json()
    assert body["connected"] is False and body["mode"] == "mock" and "token" not in str(body).lower()


async def test_connect_redirects_to_swiggy_and_callback_finishes_login(swiggy_api, browser):
    r = await swiggy_api.get("/api/swiggy/connect")
    assert r.status_code == 302 and r.headers["location"].startswith("http://swiggy.test/auth/authorize?")
    code, state = await browser(r.headers["location"])
    done = await swiggy_api.get("/api/swiggy/callback", params={"code": code, "state": state})
    assert done.status_code == 200 and "connected" in done.text
    assert (await swiggy_api.get("/api/swiggy/status")).json()["connected"] is True
    assert (await swiggy_api.post("/api/swiggy/disconnect")).status_code == 204
    assert (await swiggy_api.get("/api/swiggy/status")).json()["connected"] is False


async def test_callback_with_unknown_state_or_denied_login_is_a_400(swiggy_api):
    r = await swiggy_api.get("/api/swiggy/callback", params={"code": "x", "state": "never-issued"})
    assert r.status_code == 400 and "no longer valid" in r.text
    r = await swiggy_api.get("/api/swiggy/callback", params={"error": "access_denied"})
    assert r.status_code == 400


async def test_connect_endpoints_vanish_when_disabled(swiggy_api):
    backend_app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, swiggy_connect_enabled=False)
    assert (await swiggy_api.get("/api/swiggy/connect")).status_code == 404
    assert (await swiggy_api.get("/api/swiggy/callback", params={"code": "x", "state": "y"})).status_code == 404
    assert (await swiggy_api.post("/api/swiggy/disconnect")).status_code == 404
    assert (await swiggy_api.get("/api/swiggy/status")).status_code == 200  # status stays readable


def test_real_platform_explains_what_is_missing(tmp_path):
    from app.platform.factory import build_platform
    p = build_platform(Settings(_env_file=None, mock_mode=False, swiggy_token_path=str(tmp_path / "t.json")))
    assert "not connected" in p.unsupported_reason()
