"""Thin HTTP client for the Mock Swiggy MCP service.

The real Swiggy MCP client (OAuth 2.1 + PKCE, etc.) is Stage 2 and will be built from
Swiggy's current official documentation. Nothing here is assumed to match Swiggy's protocol.
"""
from __future__ import annotations

import httpx

from .base import PlatformError, PlatformResult


class MockMCPClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None, timeout: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def call_tool(self, name: str, arguments: dict | None = None) -> PlatformResult:
        try:
            resp = await self._client.post(f"{self._base_url}/tools/call",
                                           json={"name": name, "arguments": arguments or {}})
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            return PlatformResult(ok=False, source="mock", synthetic=True,
                                  error=PlatformError(code="mcp_unavailable",
                                                      message=f"Mock MCP unreachable: {type(e).__name__}"))
        err = body.get("error")
        return PlatformResult(ok=bool(body.get("ok")), source="mock", synthetic=True,
                              data=body.get("data"),
                              error=PlatformError(**err) if err else None)

    async def health(self) -> bool:
        try:
            r = await self._client.get(f"{self._base_url}/health")
            return r.status_code == 200
        except httpx.HTTPError:
            return False
