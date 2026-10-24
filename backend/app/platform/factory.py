from __future__ import annotations

from functools import lru_cache

from ..config import Settings, get_settings
from .base import SwiggyPlatform
from .mcp_client import MockMCPClient
from .mock_platform import MockSwiggyPlatform
from .real_platform import RealSwiggyPlatform
from .swiggy.runtime import get_food_mcp, is_connected


def build_platform(settings: Settings) -> SwiggyPlatform:
    if settings.mock_mode:
        return MockSwiggyPlatform(MockMCPClient(settings.mock_mcp_url))
    return RealSwiggyPlatform(is_connected=lambda: is_connected(settings), client=get_food_mcp())


@lru_cache
def get_platform() -> SwiggyPlatform:
    return build_platform(get_settings())
