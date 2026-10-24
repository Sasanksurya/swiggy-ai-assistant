import os
import sys
from pathlib import Path

import httpx
import pytest

# Tests never send traces, even if a developer has LANGSMITH_TRACING=true in their shell.
os.environ["LANGSMITH_TRACING"] = "false"

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mock-mcp"))

from mock_swiggy_mcp.app import app as mock_app  # noqa: E402
from mock_swiggy_mcp.tools import reset_state  # noqa: E402

from app.main import app as backend_app  # noqa: E402
from app.platform.factory import get_platform  # noqa: E402
from app.platform.mcp_client import MockMCPClient  # noqa: E402
from app.platform.mock_platform import MockSwiggyPlatform  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_state():
    reset_state()
    yield
    reset_state()


@pytest.fixture
def platform():
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://mock")
    return MockSwiggyPlatform(MockMCPClient("http://mock", client=client))


@pytest.fixture
async def api(platform):
    backend_app.dependency_overrides[get_platform] = lambda: platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=backend_app),
                                 base_url="http://test") as c:
        yield c
    backend_app.dependency_overrides.clear()


@pytest.fixture
def assistant(platform):
    from app.assistant.nlu import RuleBasedNLU
    from app.assistant.service import AssistantService
    from app.assistant.session_store import InMemorySessionStore
    return AssistantService(platform, RuleBasedNLU(), InMemorySessionStore())


@pytest.fixture
async def chat_api(assistant, platform):
    from app.assistant.factory import get_assistant
    backend_app.dependency_overrides[get_assistant] = lambda: assistant
    backend_app.dependency_overrides[get_platform] = lambda: platform  # same platform as the assistant
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=backend_app),
                                 base_url="http://test") as c:
        yield c
    backend_app.dependency_overrides.clear()


# ----- fake Swiggy (OAuth + Food MCP) used by the swiggy connection-layer tests -----
@pytest.fixture
def fake_swiggy():
    from tests.fake_swiggy import FakeSwiggy
    return FakeSwiggy()


@pytest.fixture
def oauth(fake_swiggy):
    from app.platform.swiggy.oauth import SwiggyOAuth
    from app.platform.swiggy.token_store import MemoryTokenStore
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=fake_swiggy.app))
    return SwiggyOAuth("http://swiggy.test", "http://localhost:8000/api/swiggy/callback",
                       MemoryTokenStore(), client=http)


@pytest.fixture
def browser(fake_swiggy):
    """Plays the user's browser: opens the authorize URL and reports where Swiggy redirects back to."""
    from urllib.parse import parse_qs, urlparse

    async def go(authorize_url: str) -> tuple[str, str]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fake_swiggy.app)) as c:
            r = await c.get(authorize_url)
        assert r.status_code == 302, r.text
        q = parse_qs(urlparse(r.headers["location"]).query)
        return q["code"][0], q["state"][0]
    return go


@pytest.fixture
async def connected(oauth, browser):
    code, state = await browser(await oauth.begin())
    await oauth.complete(code, state)
    return oauth
