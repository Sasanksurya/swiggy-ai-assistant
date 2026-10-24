"""Mapping and the read-only real platform, using response shapes recorded from the real Swiggy server
(values replaced with neutral test data)."""
import pytest

from app.platform.real_platform import LIVE_CAPABILITIES, RealSwiggyPlatform
from app.platform.swiggy.mapping import (
    MappingError,
    map_addresses,
    map_menu,
    map_restaurants,
    parse_rupees,
)
from app.platform.swiggy.mcp_http import McpToolError, McpUnavailable
from app.platform.swiggy.oauth import NotConnected

ADDRESSES = {"addresses": [
    {"id": "a1", "addressLine": "1 Test Road", "phoneNumber": "9999999999", "addressCategory": "HOME",
     "addressTag": "Home"},
    {"id": "a2", "addressLine": "2 Test Road", "phoneNumber": "9999999999", "addressCategory": "WORK"}],
    "total": 2, "resolution": {"needsUserClarification": True, "defaultAddressId": "a2"}}

SEARCH = {"restaurants": [
    {"id": 101, "name": "Test Biryani (Ad)", "cuisines": ["Biryani", "Kebabs"], "avgRating": 3.8,
     "costForTwo": "₹500 for two", "areaName": "Hitech City", "deliveryTimeMinutes": 32,
     "availabilityStatus": "OPEN"},
    {"id": "102", "name": "Closed Place", "cuisines": ["Biryani"], "avgRating": 4.1, "costForTwo": "₹300 for two",
     "areaName": "Madhapur", "deliveryTimeMinutes": 20, "availabilityStatus": "CLOSED"},
    {"id": "103", "name": "No Price", "cuisines": [], "deliveryTimeMinutes": 10, "availabilityStatus": "OPEN"},
    "junk"], "total": 4}


def _menu(items_by_category, has_more=False):
    return {"restaurant": {"id": "101", "name": "Test Biryani", "areaName": "Hitech City", "cuisines": ["Biryani"],
                           "avgRating": 3.8, "costForTwoMessage": "₹500 for two", "isOpen": True,
                           "deliveryTime": 30, "address": "secret street"},
            "categories": [{"title": t, "items": i} for t, i in items_by_category.items()],
            "page": 1, "hasMore": has_more}


def _item(i, name, price, veg, **kw):
    return {"id": i, "name": name, "price": price, "inStock": 1, "isVeg": veg, "hasVariants": True, **kw}


MENU = _menu({"Recommended": [_item("1", "Chicken Biryani", 369, False, isBestseller=True),
                              _item("2", "Paneer Biryani", 349, True)],
              "Biryani": [_item("1", "Chicken Biryani", 369, False), _item("3", "Mutton Biryani", 539, False,
                                                                           inStock=0)]})


def test_restaurants_are_mapped_and_unusable_rows_dropped():
    rows = map_restaurants(SEARCH)
    assert [r["id"] for r in rows] == ["101", "102"]  # numeric id becomes text; no-price row and junk dropped
    first = rows[0]
    assert first == {"id": "101", "name": "Test Biryani", "cuisines": ["Biryani", "Kebabs"], "area": "Hitech City",
                     "rating": 3.8, "delivery_time_min": 32, "price_for_two_inr": 500, "is_open": True,
                     "sponsored": True}
    assert rows[1]["is_open"] is False and rows[1]["sponsored"] is False


@pytest.mark.parametrize("bad", [None, [], {}, {"restaurants": "x"}])
def test_unexpected_restaurant_payloads_raise(bad):
    with pytest.raises(MappingError):
        map_restaurants(bad)


def test_parse_rupees_is_strict():
    assert parse_rupees("₹500 for two") == 500 and parse_rupees("₹1,200") == 1200
    assert parse_rupees("about 500") is None and parse_rupees("₹5 to ₹10") is None and parse_rupees(500) is None


def test_menu_dedupes_and_keeps_required_fields_only():
    restaurant, items, more = map_menu(MENU)
    assert restaurant["id"] == "101" and restaurant["price_for_two_inr"] == 500 and not more
    assert [i["id"] for i in items] == ["1", "2", "3"]  # dish "1" appears in two categories
    chicken, paneer, mutton = items
    assert chicken == {"id": "1", "restaurant_id": "101", "name": "Chicken Biryani", "price_inr": 369, "veg": False,
                       "category": "Recommended", "available": True, "has_options": True}
    assert paneer["veg"] is True and mutton["available"] is False
    assert "address" not in str(restaurant)  # raw street address is never copied through


def test_menu_drops_items_with_unclear_price_or_veg_flag():
    raw = _menu({"X": [_item("1", "A", 99.5, True), _item("2", "B", "99", True), _item("3", "C", 99, None),
                       _item("4", "D", 99, True)]})
    assert [i["id"] for i in map_menu(raw)[1]] == ["4"]


def test_menu_with_unexpected_shape_raises():
    with pytest.raises(MappingError):
        map_menu({"restaurant": {"id": "1"}, "categories": []})
    with pytest.raises(MappingError):
        map_menu({"categories": []})


def test_addresses_drop_phone_and_pick_swiggys_default():
    rows, default = map_addresses(ADDRESSES)
    assert default == "a2" and [a["id"] for a in rows] == ["a1", "a2"]
    assert "9999999999" not in str(rows) and rows[0]["category"] == "HOME"
    assert map_addresses({"addresses": ADDRESSES["addresses"], "resolution": {"defaultAddressId": "zzz"}})[1] is None


class StubClient:
    def __init__(self, **responses):
        self.responses, self.calls = responses, []

    async def call_tool(self, name, arguments=None, *, idempotent=True):
        self.calls.append((name, dict(arguments or {}), idempotent))
        r = self.responses[name]
        if isinstance(r, Exception):
            raise r
        return r


def _platform(**responses):
    stub = StubClient(get_addresses=ADDRESSES, **responses)
    return RealSwiggyPlatform(is_connected=lambda: True, client=stub), stub


async def test_capabilities_are_live_only_for_the_mapped_reads():
    p, _ = _platform()
    assert {c for c, ok in p.capabilities().items() if ok} == LIVE_CAPABILITIES
    assert not RealSwiggyPlatform(is_connected=lambda: False, client=StubClient()).capabilities()["get_menu"]
    assert not RealSwiggyPlatform(is_connected=lambda: True).capabilities()["get_menu"]  # no client, no live data


async def test_search_uses_the_default_address_and_filters_locally():
    p, stub = _platform(search_restaurants=SEARCH)
    res = await p.search_restaurants("biryani", open_only=True, max_price_for_two_inr=600)
    assert res.ok and res.source == "swiggy" and res.synthetic is False and [r["id"] for r in res.data] == ["101"]
    assert stub.calls[1] == ("search_restaurants", {"addressId": "a2", "query": "biryani"}, True)
    await p.search_restaurants("biryani")
    assert [c[0] for c in stub.calls].count("get_addresses") == 1  # address looked up once


async def test_search_without_a_query_asks_instead_of_guessing():
    p, stub = _platform(search_restaurants=SEARCH)
    res = await p.search_restaurants("  ")
    assert not res.ok and res.error.code == "invalid_argument" and stub.calls == []


async def test_menu_is_paged_and_bounded():
    page = _menu({"C": [_item("9", "More", 100, True)]}, has_more=True)
    p, stub = _platform(get_restaurant_menu=page)
    res = await p.get_menu("101")
    assert res.ok and res.data["partial"] is True
    pages = [c[1]["page"] for c in stub.calls if c[0] == "get_restaurant_menu"]
    assert pages == [1, 2, 3]


async def test_search_menu_filters_by_words_price_veg_and_stock():
    p, _ = _platform(search_restaurants=SEARCH, get_restaurant_menu=MENU)
    res = await p.search_menu(query="biryani", max_price_inr=400, veg_only=True)
    assert res.ok and [i["name"] for i in res.data] == ["Paneer Biryani"]
    res = await p.search_menu(query="mutton biryani", restaurant_id="101", available_only=False)
    assert [i["id"] for i in res.data] == ["3"]
    res = await p.search_menu(query="mutton biryani", restaurant_id="101")
    assert res.data == []  # out of stock is hidden by default


@pytest.mark.parametrize("err,code", [
    (McpToolError("Restaurant closed"), "upstream_error"),
    (McpUnavailable("down"), "mcp_unavailable"),
    (NotConnected("expired"), "not_connected")])
async def test_failures_become_clean_results(err, code):
    p, _ = _platform(search_restaurants=err)
    res = await p.search_restaurants("biryani")
    assert not res.ok and res.error.code == code and res.data is None


async def test_unrecognised_response_is_reported_not_guessed():
    p, _ = _platform(search_restaurants={"unexpected": True})
    res = await p.search_restaurants("biryani")
    assert not res.ok and res.error.code == "unexpected_response"


async def test_no_write_tool_is_ever_called():
    p, stub = _platform(search_restaurants=SEARCH, get_restaurant_menu=MENU)
    await p.search_restaurants("biryani")
    await p.get_menu("101")
    await p.search_menu(query="biryani")
    await p.get_addresses()
    for write in (p.add_to_cart("1"), p.update_cart("1", 2), p.remove_from_cart("1"), p.place_order("a2"),
                  p.get_cart(), p.get_order_status("o1")):
        r = await write
        assert not r.ok and r.error.code == "unsupported_capability"
    assert {c[0] for c in stub.calls} <= {"get_addresses", "search_restaurants", "get_restaurant_menu"}
