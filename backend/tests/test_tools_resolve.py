import pytest

from app.assistant.resolve import match_by_name, pick_by_index
from app.assistant.state import Ref
from app.assistant.tools import ToolRunner
from app.platform.real_platform import RealSwiggyPlatform

REFS = [Ref(id="m-002-01", name="Masala Dosa"), Ref(id="m-002-02", name="Idli (3 pc)"),
        Ref(id="m-001-02", name="Veg Biryani")]


def test_pick_by_index():
    assert pick_by_index(REFS, 1).name == "Masala Dosa"
    assert pick_by_index(REFS, -1).name == "Veg Biryani"
    assert pick_by_index(REFS, 9) is None and pick_by_index(REFS, 0) is None
    assert pick_by_index([], 1) is None and pick_by_index(REFS, None) is None


def test_match_by_name():
    assert [r.id for r in match_by_name(REFS, "dosa")] == ["m-002-01"]
    assert [r.id for r in match_by_name(REFS, "veg biryani")] == ["m-001-02"]
    assert [r.id for r in match_by_name(REFS, "idli")] == ["m-002-02"]
    assert match_by_name(REFS, "pizza") == [] and match_by_name(REFS, None) == []
    assert [r.id for r in match_by_name(REFS, "m-002-02")] == ["m-002-02"]


async def test_runner_calls_platform_and_logs(platform):
    run = ToolRunner(platform, "sess-1")
    r = await run.call("search_restaurants", query="pizza")
    assert r.ok and r.data[0]["id"] == "r-003"
    assert run.calls[0].name == "search_restaurants" and run.calls[0].ok


async def test_runner_injects_session_id_for_cart(platform):
    run = ToolRunner(platform, "sess-A")
    await run.call("add_to_cart", item_id="m-002-01", quantity=1)
    assert (await ToolRunner(platform, "sess-A").call("get_cart")).data["lines"]
    assert not (await ToolRunner(platform, "sess-B").call("get_cart")).data["lines"]


async def test_runner_rejects_non_capability_names(platform):
    with pytest.raises(ValueError):
        await ToolRunner(platform, "s").call("cancel_order")  # Swiggy has no cancel tool, so we have none either


async def test_runner_never_calls_undeclared_capability():
    run = ToolRunner(RealSwiggyPlatform(), "s")
    r = await run.call("search_restaurants", query="x")
    assert not r.ok and r.error.code == "unsupported_capability" and r.data is None
    assert run.calls[0].error_code == "unsupported_capability"


async def test_runner_logs_failures(platform):
    run = ToolRunner(platform, "s")
    r = await run.call("get_item_details", item_id="nope")
    assert not r.ok and run.calls[0].error_code == "not_found"
