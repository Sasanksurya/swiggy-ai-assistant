import sys
from pathlib import Path

import httpx
import pytest

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
