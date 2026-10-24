"""Shared instances of the Swiggy connection layer, built from Settings."""
from __future__ import annotations

from functools import lru_cache

from ...config import Settings, get_settings
from .mcp_http import McpHttpClient
from .oauth import SwiggyOAuth
from .token_store import FileTokenStore


def food_mcp_url(settings: Settings) -> str:
    return f"{settings.swiggy_base_url.rstrip('/')}/food"


@lru_cache
def get_oauth() -> SwiggyOAuth:
    s = get_settings()
    return SwiggyOAuth(s.swiggy_base_url, s.swiggy_redirect_uri, FileTokenStore(s.swiggy_token_path))


@lru_cache
def get_food_mcp() -> McpHttpClient:
    oauth = get_oauth()
    return McpHttpClient(food_mcp_url(get_settings()), oauth.get_access_token, oauth.refresh)


def is_connected(settings: Settings) -> bool:
    """Cheap, offline check used to explain why the real platform has nothing to offer yet."""
    return FileTokenStore(settings.swiggy_token_path).load().tokens is not None
