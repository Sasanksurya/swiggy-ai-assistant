import pytest

from app.platform.swiggy.doctor import (
    READ_ONLY_TOOLS,
    ReadOnlyTools,
    describe_tools,
    find_first,
    first_open_restaurant_id,
    redact,
    schema_args,
)


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


async def test_doctor_allows_only_the_read_tools():
    rec = _Recorder()
    for t in sorted(READ_ONLY_TOOLS):
        await ReadOnlyTools(rec).call(t)
    assert sorted(rec.calls) == sorted(READ_ONLY_TOOLS)
    assert READ_ONLY_TOOLS == {"get_addresses", "search_restaurants", "get_restaurant_menu", "get_food_cart",
                               "search_menu", "get_food_orders", "fetch_food_coupons"}
    assert not {t for t in READ_ONLY_TOOLS if t.startswith(("update", "place", "flush", "apply", "create",
                                                              "delete", "cancel", "book", "checkout"))}


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


_SCHEMA = {"type": "object", "properties": {"addressId": {"type": "string"}, "restaurantId": {"type": "string"},
                                            "query": {"type": "string"}, "page": {"type": "number"}},
           "required": ["addressId", "restaurantId"]}


def test_schema_args_fill_only_what_we_know_and_report_the_rest():
    args, missing = schema_args(_SCHEMA, {"addressId": "a1", "query": "biryani", "unrelated": 1})
    assert args == {"addressId": "a1", "query": "biryani"} and missing == ["restaurantId"]
    args, missing = schema_args(_SCHEMA, {"addressId": "a1", "restaurantId": "r1"})
    assert args == {"addressId": "a1", "restaurantId": "r1"} and missing == []
    assert schema_args({}, {"addressId": "a1"}) == ({}, [])


def test_first_open_restaurant_prefers_open_ones():
    data = {"restaurants": [{"id": "1", "availabilityStatus": "CLOSED"}, {"id": "2", "availabilityStatus": "OPEN"}]}
    assert first_open_restaurant_id(data) == "2"
    assert first_open_restaurant_id({"restaurants": []}) is None


def test_describe_tools_shows_required_flags_and_enums():
    text = describe_tools([{"name": "create_address", "description": "Adds   an address.", "inputSchema": {
        "properties": {"city": {"type": "string"}, "addressCategory": {"type": "string", "enum": ["Home", "Work"]}},
        "required": ["city"]}}])
    assert "* create_address" in text and "city (string, REQUIRED)" in text
    assert "addressCategory (string one of Home/Work, optional)" in text and "Adds an address." in text


def test_session_identifiers_are_redacted():
    out = redact({"tid": "eyJhbGciOi.payload", "sid": "abc", "deviceId": "x", "statusCode": 0, "successful": True})
    assert out == {"tid": "<redacted>", "sid": "<redacted>", "deviceId": "<redacted>", "statusCode": 0,
                   "successful": True}
