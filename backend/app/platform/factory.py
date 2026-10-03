from __future__ import annotations

from functools import lru_cache

from ..config import Settings, get_settings
from .base import SwiggyPlatform
from .mcp_client import MockMCPClient
from .mock_platform import MockSwiggyPlatform
from .real_platform import RealSwiggyPlatform


def build_platform(settings: Settings) -> SwiggyPlatform:
    if settings.mock_mode:
        return MockSwiggyPlatform(MockMCPClient(settings.mock_mcp_url))
    return RealSwiggyPlatform()


@lru_cache
def get_platform() -> SwiggyPlatform:
    return build_platform(get_settings())
