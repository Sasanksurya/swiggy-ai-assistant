import httpx
import pytest

from app.platform.swiggy.mcp_http import (
    McpAuthError,
    McpHttpClient,
    McpToolError,
    McpUnavailable,
)
from tests.fake_swiggy import ADDRESSES


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def mcp(connected, fake_swiggy, sleeps):
    async def fake_sleep(s):
        sleeps.append(s)
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=fake_swiggy.app))
    return McpHttpClient("http://swiggy.test/food", connected.get_access_token, connected.refresh,
                         client=http, sleep=fake_sleep)


async def test_handshake_then_tool_call_and_session_reuse(mcp, fake_swiggy):
    assert await mcp.call_tool("get_addresses") == {"success": True, "data": ADDRESSES}
    await mcp.call_tool("get_addresses")
    assert fake_swiggy.rpc_calls == ["initialize", "notifications/initialized", "tools/call", "tools/call"]


async def test_list_tools(mcp):
    assert [t["name"] for t in await mcp.list_tools()] == ["get_addresses", "place_food_order"]


async def test_streamed_sse_answer_is_parsed(mcp, fake_swiggy):
    fake_swiggy.use_sse = True
    assert (await mcp.call_tool("get_addresses"))["success"] is True


async def test_tool_failure_is_a_tool_error_not_a_retry(mcp, fake_swiggy):
    with pytest.raises(McpToolError, match="Restaurant closed"):
        await mcp.call_tool("tool_error")
    assert fake_swiggy.rpc_calls.count("tools/call") == 1


async def test_unknown_tool_is_a_tool_error(mcp):
    with pytest.raises(McpToolError) as e:
        await mcp.call_tool("does_not_exist")
    assert e.value.code == -32602


async def test_expired_token_is_refreshed_once_then_call_succeeds(mcp, fake_swiggy):
    await mcp.call_tool("get_addresses")
    fake_swiggy.access.clear()  # Swiggy now rejects the old access token with 401
    assert (await mcp.call_tool("get_addresses"))["success"] is True
    assert fake_swiggy.refresh_calls == 1


async def test_auth_failure_after_refresh_is_not_retried_forever(mcp, fake_swiggy):
    with pytest.raises(McpAuthError):
        await mcp.call_tool("auth_error")  # JSON-RPC -32001 every time
    assert fake_swiggy.refresh_calls == 1


async def test_rate_limit_waits_for_retry_after_only(mcp, fake_swiggy, sleeps):
    fake_swiggy.fail_next = [(429, {"retry-after": "3"})]
    assert (await mcp.call_tool("get_addresses"))["success"] is True
    assert sleeps == [3.0]  # exactly Retry-After, no extra backoff on top


async def test_server_error_retried_with_backoff_for_idempotent_calls(mcp, fake_swiggy, sleeps):
    fake_swiggy.fail_next = [(503, {}), (503, {})]
    assert (await mcp.call_tool("get_addresses"))["success"] is True
    assert sleeps == [0.5, 1.0]


async def test_gives_up_after_four_attempts(mcp, fake_swiggy, sleeps):
    fake_swiggy.fail_next = [(503, {})] * 10
    with pytest.raises(McpUnavailable):
        await mcp.call_tool("get_addresses")
    assert sleeps == [0.5, 1.0, 2.0]
    assert len(fake_swiggy.fail_next) == 6  # 4 attempts consumed 4 failures


async def test_order_placement_is_never_blindly_retried(mcp, fake_swiggy, sleeps):
    await mcp.call_tool("get_addresses")  # handshake done, so only the order call can hit the failure
    fake_swiggy.fail_next = [(503, {})]
    with pytest.raises(McpUnavailable):
        await mcp.call_tool("place_food_order", {"paymentMethod": "COD"}, idempotent=False)
    assert sleeps == [] and fake_swiggy.rpc_calls.count("tools/call") == 1  # the order was not re-sent


async def test_forgotten_session_triggers_a_new_handshake(mcp, fake_swiggy):
    await mcp.call_tool("get_addresses")
    fake_swiggy.drop_sessions_once = True
    assert (await mcp.call_tool("get_addresses"))["success"] is True
    assert fake_swiggy.rpc_calls.count("initialize") == 2
