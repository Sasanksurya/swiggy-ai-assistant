import pytest

from app.platform.swiggy.doctor import READ_ONLY_TOOLS, ReadOnlyTools, find_first, redact


class _Recorder:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments=None):
        self.calls.append(name)
        return {"ok": True}


@pytest.mark.parametrize("tool", ["update_food_cart", "place_food_order", "flush_food_cart", "apply_food_coupon",
                                  "create_address", "checkout", "book_table"])
async def test_doctor_refuses_every_tool_that_could_change_something(tool):
    rec = _Recorder()
    with pytest.raises(PermissionError):
        await ReadOnlyTools(rec).call(tool, {})
    assert rec.calls == []


async def test_doctor_allows_only_the_four_read_tools():
    rec = _Recorder()
    for t in sorted(READ_ONLY_TOOLS):
        await ReadOnlyTools(rec).call(t)
    assert sorted(rec.calls) == sorted(READ_ONLY_TOOLS) and len(READ_ONLY_TOOLS) == 4


def test_redact_removes_personal_data_but_keeps_structure():
    data = {"userPhone": "9876543210", "email": "a@b.c", "lat": 17.38, "restaurant": {"name": "Spice Hub", "rating": 4.2},
            "deliveryAddress": {"line1": "12 Some Street", "city": "Hyderabad"}, "related": ["x"], "isOpen": True,
            "note": "call 9876543210 now"}
    out = redact(data)
    assert out["userPhone"] == out["email"] == out["lat"] == "<redacted>"
    assert out["deliveryAddress"] == {"line1": "<redacted>", "city": "<redacted>"}  # nested under a sensitive key
    assert out["restaurant"] == {"name": "Spice Hub", "rating": 4.2}  # shape-learning data stays
    assert out["related"] == ["x"] and out["isOpen"] is True  # 'related' contains 'lat' but is not a sensitive word
    assert "9876543210" not in out["note"]


def test_redact_truncates_long_lists_and_strict_blanks_all_strings():
    out = redact({"items": list(range(10))})
    assert out["items"][:3] == [0, 1, 2] and "7 more" in out["items"][3]
    assert redact({"label": "Home", "n": 3}, strict=True) == {"label": "<redacted>", "n": 3}


def test_find_first_searches_nested_data():
    assert find_first({"data": [{"x": 1}, {"restaurantId": "r9"}]}, ("restaurantId", "id")) == "r9"
    assert find_first({"data": []}, ("id",)) is None
