"""Platform abstraction. Agents, workflows and the budget engine depend ONLY on this module."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel


class PlatformError(BaseModel):
    code: str  # e.g. not_found, unsupported_capability, mcp_unavailable, invalid_argument
    message: str


class PlatformResult(BaseModel):
    ok: bool
    source: Literal["mock", "swiggy"]
    synthetic: bool  # True whenever data is not from the authorized Swiggy MCP
    data: Any = None
    error: PlatformError | None = None


def unsupported(source: Literal["mock", "swiggy"], capability: str, reason: str | None = None) -> PlatformResult:
    return PlatformResult(
        ok=False, source=source, synthetic=(source == "mock"),
        error=PlatformError(code="unsupported_capability",
                            message=reason or f"Capability '{capability}' is not available"),
    )


CAPABILITIES = (
    "search_restaurants", "get_restaurant_details", "search_menu", "get_menu", "get_item_details",
    "get_cart", "add_to_cart", "update_cart", "remove_from_cart", "get_order_status", "get_order_details",
)


class SwiggyPlatform(ABC):
    """Interface mirrored from the project spec. Unavailable capabilities must return
    an `unsupported_capability` result, never fabricated data."""

    source: Literal["mock", "swiggy"]

    @abstractmethod
    def capabilities(self) -> dict[str, bool]: ...

    @abstractmethod
    async def search_restaurants(self, query: str = "", cuisine: str | None = None,
                                 max_price_for_two_inr: int | None = None,
                                 open_only: bool = False) -> PlatformResult: ...

    @abstractmethod
    async def get_restaurant_details(self, restaurant_id: str) -> PlatformResult: ...

    @abstractmethod
    async def search_menu(self, query: str = "", restaurant_id: str | None = None,
                          max_price_inr: int | None = None, veg_only: bool = False,
                          available_only: bool = True) -> PlatformResult: ...

    @abstractmethod
    async def get_menu(self, restaurant_id: str) -> PlatformResult: ...

    @abstractmethod
    async def get_item_details(self, item_id: str) -> PlatformResult: ...

    @abstractmethod
    async def get_cart(self, session_id: str = "default") -> PlatformResult: ...

    @abstractmethod
    async def add_to_cart(self, item_id: str, quantity: int = 1,
                          session_id: str = "default") -> PlatformResult: ...

    @abstractmethod
    async def update_cart(self, item_id: str, quantity: int,
                          session_id: str = "default") -> PlatformResult: ...

    @abstractmethod
    async def remove_from_cart(self, item_id: str, session_id: str = "default") -> PlatformResult: ...

    @abstractmethod
    async def get_order_status(self, order_id: str) -> PlatformResult: ...

    @abstractmethod
    async def get_order_details(self, order_id: str) -> PlatformResult: ...
