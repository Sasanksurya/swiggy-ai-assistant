"""The authorized Swiggy MCP (Builders Club), read-only for now.

Live today: addresses, restaurant search, restaurant details and menus (mapped from responses recorded with
the doctor command, see platform/swiggy/mapping.py). Everything that changes something or whose real response
shape has not been recorded (cart, order status, item lookup, placing orders) still reports
`unsupported_capability`. Nothing is faked, and no write tool is called from this class.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from .base import CAPABILITIES, PlatformError, PlatformResult, SwiggyPlatform, unsupported
from .swiggy.mapping import MappingError, map_addresses, map_menu, map_restaurants
from .swiggy.mcp_http import McpAuthError, McpError, McpHttpClient, McpToolError
from .swiggy.oauth import NotConnected

log = logging.getLogger("swiggy.platform")

_NOT_CONNECTED = ("Your Swiggy account is not connected yet. Open /api/swiggy/connect to sign in "
                  "(Swiggy MCP access is invite-based, see docs/SWIGGY_ACCESS.md).")
_READ_ONLY = ("I can browse real Swiggy restaurants and menus, but cart and ordering are not enabled in this "
              "version yet.")
_NOT_MAPPED = ("Your Swiggy account is connected, but this version does not map Swiggy's responses yet. "
               "Next step: record real responses with the doctor command (docs/SWIGGY_ACCESS.md).")

LIVE_CAPABILITIES = frozenset({"search_restaurants", "get_restaurant_details", "search_menu", "get_menu",
                               "get_addresses"})
MAX_MENU_PAGES = 3        # Swiggy pages menus by category; three pages cover the popular sections
MAX_SEARCH_MENUS = 3      # restaurants whose menus are searched for a dish query


class RealSwiggyPlatform(SwiggyPlatform):
    source = "swiggy"

    def __init__(self, is_connected: Callable[[], bool] | None = None, client: McpHttpClient | None = None):
        self._is_connected = is_connected
        self._client = client
        self._address_id: str | None = None

    # ----- what is available -----
    def _live(self) -> bool:
        return self._client is not None and bool(self._is_connected and self._is_connected())

    def capabilities(self) -> dict[str, bool]:
        live = self._live()
        return {c: live and c in LIVE_CAPABILITIES for c in CAPABILITIES}

    def unsupported_reason(self) -> str | None:
        if not (self._is_connected and self._is_connected()):
            return _NOT_CONNECTED
        return _READ_ONLY if self._client is not None else _NOT_MAPPED

    def _no(self, name: str) -> PlatformResult:
        return unsupported("swiggy", name, self.unsupported_reason())

    @staticmethod
    def _fail(code: str, message: str) -> PlatformResult:
        return PlatformResult(ok=False, source="swiggy", synthetic=False,
                              error=PlatformError(code=code, message=message))

    @staticmethod
    def _ok(data: Any) -> PlatformResult:
        return PlatformResult(ok=True, source="swiggy", synthetic=False, data=data)

    # ----- one read-only call, errors turned into results -----
    async def _read(self, tool: str, arguments: dict) -> Any:
        assert self._client is not None
        return await self._client.call_tool(tool, arguments, idempotent=True)

    def _error_result(self, e: Exception) -> PlatformResult:
        if isinstance(e, (NotConnected, McpAuthError)):
            return self._fail("not_connected", "Your Swiggy sign-in has expired. Open /api/swiggy/connect to "
                                               "sign in again.")
        if isinstance(e, MappingError):
            log.warning("unexpected Swiggy response: %s", e)
            return self._fail("unexpected_response", "Swiggy answered in a format this version does not "
                                                     "recognise, so I will not guess.")
        if isinstance(e, McpToolError):
            return self._fail("upstream_error", f"Swiggy could not do that: {e.message[:200]}")
        return self._fail("mcp_unavailable", "I couldn't reach Swiggy. Please try again in a moment.")

    async def _default_address(self) -> str:
        """Id of the user's default saved address, as chosen by Swiggy. Browsing needs one."""
        if self._address_id is None:
            addresses, default = map_addresses(await self._read("get_addresses", {}))
            chosen = default or (addresses[0]["id"] if len(addresses) == 1 else None)
            if chosen is None:
                raise MappingError("get_addresses: no default address to browse from")
            self._address_id = chosen
        return self._address_id

    # ----- live capabilities -----
    async def get_addresses(self) -> PlatformResult:
        if not self._live():
            return self._no("get_addresses")
        try:
            addresses, _ = map_addresses(await self._read("get_addresses", {}))
            return self._ok(addresses)
        except (McpError, NotConnected, MappingError) as e:
            return self._error_result(e)

    async def search_restaurants(self, query="", cuisine=None, max_price_for_two_inr=None, open_only=False):
        if not self._live():
            return self._no("search_restaurants")
        if not (query or "").strip():
            return self._fail("invalid_argument", "Tell me what you'd like to eat (for example biryani) and I "
                                                  "will search Swiggy.")
        try:
            rows = map_restaurants(await self._read("search_restaurants", {
                "addressId": await self._default_address(), "query": query.strip()}))
        except (McpError, NotConnected, MappingError) as e:
            return self._error_result(e)
        if cuisine:
            rows = [r for r in rows if cuisine.lower() in (c.lower() for c in r["cuisines"])]
        if max_price_for_two_inr is not None:
            rows = [r for r in rows if r["price_for_two_inr"] <= max_price_for_two_inr]
        if open_only:
            rows = [r for r in rows if r["is_open"]]
        return self._ok(rows)

    async def _menu(self, restaurant_id: str) -> tuple[dict, list[dict], bool]:
        address = await self._default_address()
        restaurant, items, seen, page = None, [], set(), 1
        while True:
            r, page_items, more = map_menu(await self._read("get_restaurant_menu", {
                "addressId": address, "restaurantId": restaurant_id, "page": page}))
            restaurant = restaurant or r
            items += [i for i in page_items if i["id"] not in seen]
            seen.update(i["id"] for i in page_items)
            if not more or page >= MAX_MENU_PAGES:
                return restaurant, items, more
            page += 1

    async def get_menu(self, restaurant_id):
        if not self._live():
            return self._no("get_menu")
        try:
            restaurant, items, partial = await self._menu(str(restaurant_id))
        except (McpError, NotConnected, MappingError) as e:
            return self._error_result(e)
        return self._ok({"restaurant": restaurant, "items": items, "partial": partial})

    async def get_restaurant_details(self, restaurant_id):
        if not self._live():
            return self._no("get_restaurant_details")
        try:
            restaurant, _, _ = await self._menu(str(restaurant_id))
        except (McpError, NotConnected, MappingError) as e:
            return self._error_result(e)
        return self._ok(restaurant)

    async def search_menu(self, query="", restaurant_id=None, max_price_inr=None, veg_only=False,
                          available_only=True):
        if not self._live():
            return self._no("search_menu")
        try:
            if restaurant_id:
                ids = [str(restaurant_id)]
            else:
                found = await self.search_restaurants(query=query)
                if not found.ok:
                    return found
                ids = [r["id"] for r in found.data if r["is_open"]][:MAX_SEARCH_MENUS]
            menus = await asyncio.gather(*(self._menu(i) for i in ids))
        except (McpError, NotConnected, MappingError) as e:
            return self._error_result(e)
        words = (query or "").lower().split()
        out = []
        for _, items, _ in menus:
            for i in items:
                text = f"{i['name']} {i['category']}".lower()
                if (all(w in text for w in words) and (max_price_inr is None or i["price_inr"] <= max_price_inr)
                        and (not veg_only or i["veg"]) and (not available_only or i["available"])):
                    out.append(i)
        return self._ok(out)

    # ----- not available yet: cart, orders, item lookup (responses not recorded, writes not enabled) -----
    async def get_item_details(self, *a, **k): return self._no("get_item_details")
    async def get_cart(self, *a, **k): return self._no("get_cart")
    async def add_to_cart(self, *a, **k): return self._no("add_to_cart")
    async def update_cart(self, *a, **k): return self._no("update_cart")
    async def remove_from_cart(self, *a, **k): return self._no("remove_from_cart")
    async def get_order_status(self, *a, **k): return self._no("get_order_status")
    async def get_order_details(self, *a, **k): return self._no("get_order_details")
    async def place_order(self, *a, **k): return self._no("place_order")
