"""Placeholder for the authorized Swiggy MCP (Stage 2).

Until the integration is built from Swiggy's current official documentation and access is
granted, every capability reports `unsupported_capability`. No endpoints, tools or fields
are assumed or invented here.
"""
from __future__ import annotations

from collections.abc import Callable

from .base import CAPABILITIES, PlatformResult, SwiggyPlatform, unsupported

_NOT_CONNECTED = ("Your Swiggy account is not connected yet. Open /api/swiggy/connect to sign in "
                  "(Swiggy MCP access is invite-based, see docs/SWIGGY_ACCESS.md).")
_NOT_MAPPED = ("Your Swiggy account is connected, but this version does not map Swiggy's responses yet. "
               "Next step: record real responses with the doctor command (docs/SWIGGY_ACCESS.md).")


class RealSwiggyPlatform(SwiggyPlatform):
    source = "swiggy"

    def __init__(self, is_connected: Callable[[], bool] | None = None):
        self._is_connected = is_connected

    def capabilities(self) -> dict[str, bool]:
        return {c: False for c in CAPABILITIES}

    def unsupported_reason(self) -> str | None:
        return _NOT_MAPPED if self._is_connected and self._is_connected() else _NOT_CONNECTED

    def _no(self, name: str) -> PlatformResult:
        return unsupported("swiggy", name, self.unsupported_reason())

    async def search_restaurants(self, *a, **k): return self._no("search_restaurants")
    async def get_restaurant_details(self, *a, **k): return self._no("get_restaurant_details")
    async def search_menu(self, *a, **k): return self._no("search_menu")
    async def get_menu(self, *a, **k): return self._no("get_menu")
    async def get_item_details(self, *a, **k): return self._no("get_item_details")
    async def get_cart(self, *a, **k): return self._no("get_cart")
    async def add_to_cart(self, *a, **k): return self._no("add_to_cart")
    async def update_cart(self, *a, **k): return self._no("update_cart")
    async def remove_from_cart(self, *a, **k): return self._no("remove_from_cart")
    async def get_order_status(self, *a, **k): return self._no("get_order_status")
    async def get_order_details(self, *a, **k): return self._no("get_order_details")
    async def get_addresses(self, *a, **k): return self._no("get_addresses")
    async def place_order(self, *a, **k): return self._no("place_order")
