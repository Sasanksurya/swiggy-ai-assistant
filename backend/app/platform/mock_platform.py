from __future__ import annotations

from .base import CAPABILITIES, SwiggyPlatform
from .mcp_client import MockMCPClient


class MockSwiggyPlatform(SwiggyPlatform):
    source = "mock"

    def __init__(self, client: MockMCPClient):
        self._c = client

    def capabilities(self) -> dict[str, bool]:
        return {c: True for c in CAPABILITIES}

    async def search_restaurants(self, query="", cuisine=None, max_price_for_two_inr=None, open_only=False):
        return await self._c.call_tool("search_restaurants", {
            "query": query, "cuisine": cuisine,
            "max_price_for_two_inr": max_price_for_two_inr, "open_only": open_only})

    async def get_restaurant_details(self, restaurant_id):
        return await self._c.call_tool("get_restaurant_details", {"restaurant_id": restaurant_id})

    async def search_menu(self, query="", restaurant_id=None, max_price_inr=None, veg_only=False,
                          available_only=True):
        return await self._c.call_tool("search_menu", {
            "query": query, "restaurant_id": restaurant_id, "max_price_inr": max_price_inr,
            "veg_only": veg_only, "available_only": available_only})

    async def get_menu(self, restaurant_id):
        return await self._c.call_tool("get_menu", {"restaurant_id": restaurant_id})

    async def get_item_details(self, item_id):
        return await self._c.call_tool("get_item_details", {"item_id": item_id})

    async def get_cart(self, session_id="default"):
        return await self._c.call_tool("get_cart", {"session_id": session_id})

    async def add_to_cart(self, item_id, quantity=1, session_id="default"):
        return await self._c.call_tool("add_to_cart", {
            "item_id": item_id, "quantity": quantity, "session_id": session_id})

    async def update_cart(self, item_id, quantity, session_id="default"):
        return await self._c.call_tool("update_cart", {
            "item_id": item_id, "quantity": quantity, "session_id": session_id})

    async def remove_from_cart(self, item_id, session_id="default"):
        return await self._c.call_tool("remove_from_cart", {"item_id": item_id, "session_id": session_id})

    async def get_order_status(self, order_id):
        return await self._c.call_tool("get_order_status", {"order_id": order_id})

    async def get_order_details(self, order_id):
        return await self._c.call_tool("get_order_details", {"order_id": order_id})

    async def get_addresses(self):
        return await self._c.call_tool("get_addresses", {})

    async def place_order(self, address_id, payment_method="COD", session_id="default"):
        return await self._c.call_tool("place_order", {
            "address_id": address_id, "payment_method": payment_method, "session_id": session_id})
