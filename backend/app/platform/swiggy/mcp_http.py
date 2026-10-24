"""Minimal MCP client over streamable HTTP (JSON-RPC 2.0), built on httpx.

Swiggy: https://mcp.swiggy.com/builders/docs/start/developer/build-an-agent/ ("standard streamable HTTP",
Bearer token on every call). Each server has its own URL, for example https://mcp.swiggy.com/food .

Retry rules come from Swiggy's go-live checklist:
  * 401 or JSON-RPC -32001 : refresh the token once and retry once, never retry with the same token
  * 429                    : wait for Retry-After (no extra backoff on top)
  * 5xx / timeout          : exponential backoff from 500 ms, at most 4 attempts and 30 s in total,
                             but ONLY for calls marked idempotent. place_food_order is not idempotent:
                             after an error the caller must check the order list before trying again.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

log = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
AUTH_ERROR_CODE = -32001


class McpError(Exception):
    """Base class. Never carries a token."""


class McpAuthError(McpError):
    """401 or JSON-RPC -32001: the access token is missing, expired or revoked."""


class McpUnavailable(McpError):
    """Network failure, timeout or 5xx. The outcome of the call is unknown."""


class McpRateLimited(McpUnavailable):
    def __init__(self, retry_after: float):
        super().__init__(f"Rate limited, retry after {retry_after:.0f}s")
        self.retry_after = retry_after


class McpToolError(McpError):
    """The server answered, but the tool call failed (invalid input, closed restaurant, minimum order...)."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.message = message
        self.code = code


class McpHttpClient:
    def __init__(self, url: str, token_provider: Callable[[], Awaitable[str]],
                 refresh_token: Callable[[], Awaitable[Any]] | None = None, *,
                 client: httpx.AsyncClient | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 max_attempts: int = 4, max_total_seconds: float = 30.0, base_delay: float = 0.5,
                 clock: Callable[[], float] = time.monotonic):
        self._url = url
        self._token = token_provider
        self._refresh = refresh_token
        self._http = client or httpx.AsyncClient(timeout=20.0, follow_redirects=False)
        self._sleep = sleep
        self._max_attempts = max_attempts
        self._max_total = max_total_seconds
        self._base_delay = base_delay
        self._clock = clock
        self._ids = itertools.count(1)
        self._session_id: str | None = None
        self._negotiated: str | None = None
        self._ready = False
        self._init_lock = asyncio.Lock()

    # ----- public -----
    async def call_tool(self, name: str, arguments: dict | None = None, *, idempotent: bool = True) -> Any:
        """Calls one tool and returns its payload (structuredContent, parsed JSON text, or raw text)."""
        result = await self._with_retries(
            "tools/call", {"name": name, "arguments": arguments or {}}, idempotent, label=f"tool {name}")
        return self._unwrap(result)

    async def list_tools(self) -> list[dict]:
        result = await self._with_retries("tools/list", {}, True, label="tools/list")
        return list(result.get("tools", []))

    # ----- retry policy -----
    async def _with_retries(self, method: str, params: dict, idempotent: bool, label: str) -> dict:
        started = self._clock()
        attempt = 0
        refreshed = False
        cid = uuid.uuid4().hex[:12]  # correlation id for our own logs (Swiggy asks partners to log one per call)
        while True:
            attempt += 1
            try:
                result = await self._request_once(method, params)
                log.info("swiggy-mcp ok cid=%s %s attempt=%d", cid, label, attempt)
                return result
            except McpAuthError:
                if refreshed or self._refresh is None:
                    log.warning("swiggy-mcp auth failed cid=%s %s", cid, label)
                    raise
                refreshed = True
                log.info("swiggy-mcp token rejected cid=%s %s, refreshing once", cid, label)
                await self._refresh()
                self._reset_session()  # the session belongs to the old token
                attempt -= 1
            except McpRateLimited as e:
                if attempt >= self._max_attempts or self._clock() - started + e.retry_after > self._max_total:
                    raise
                log.warning("swiggy-mcp 429 cid=%s %s waiting %.1fs", cid, label, e.retry_after)
                await self._sleep(e.retry_after)
            except McpUnavailable:
                delay = self._base_delay * (2 ** (attempt - 1))
                if (not idempotent or attempt >= self._max_attempts
                        or self._clock() - started + delay > self._max_total):
                    log.warning("swiggy-mcp unavailable cid=%s %s attempt=%d idempotent=%s",
                                cid, label, attempt, idempotent)
                    raise
                await self._sleep(delay)

    # ----- one HTTP exchange -----
    async def _request_once(self, method: str, params: dict) -> dict:
        await self._ensure_session()
        try:
            return await self._rpc(method, params)
        except _SessionExpired:
            self._reset_session()  # server forgot our session: handshake again, once
            await self._ensure_session()
            try:
                return await self._rpc(method, params)
            except _SessionExpired as e:
                raise McpUnavailable("MCP session could not be re-established") from e

    def _reset_session(self) -> None:
        self._ready = False
        self._session_id = None

    async def _ensure_session(self) -> None:
        async with self._init_lock:
            if self._ready:
                return
            resp = await self._post({"jsonrpc": "2.0", "id": next(self._ids), "method": "initialize",
                                     "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                                "clientInfo": {"name": "swiggy-ai-assistant", "version": "0.1.0"}}},
                                    with_session=False)
            result = self._result_or_raise(await self._read_message(resp))
            self._negotiated = result.get("protocolVersion", PROTOCOL_VERSION)
            self._session_id = resp.headers.get("mcp-session-id")  # None when the server is stateless
            self._ready = True
            await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def _rpc(self, method: str, params: dict) -> dict:
        resp = await self._post({"jsonrpc": "2.0", "id": (rid := next(self._ids)), "method": method,
                                 "params": params})
        message = await self._read_message(resp, want_id=rid)
        return self._result_or_raise(message)

    async def _post(self, payload: dict, *, with_session: bool = True) -> httpx.Response:
        headers = {"Authorization": f"Bearer {await self._token()}", "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if with_session and self._negotiated:
            headers["MCP-Protocol-Version"] = self._negotiated
        if with_session and self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            resp = await self._http.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise McpUnavailable(f"Swiggy MCP unreachable ({type(e).__name__})") from e
        if resp.status_code == 401:
            raise McpAuthError("Swiggy rejected the access token (401)")
        if resp.status_code == 404 and with_session and self._session_id:
            raise _SessionExpired()
        if resp.status_code == 429:
            raise McpRateLimited(_retry_after(resp))
        if resp.status_code >= 500:
            raise McpUnavailable(f"Swiggy MCP error {resp.status_code}")
        if resp.status_code >= 400:
            raise McpError(f"Swiggy MCP rejected the request ({resp.status_code})")
        return resp

    async def _read_message(self, resp: httpx.Response, want_id: int | None = None) -> dict:
        ctype = resp.headers.get("content-type", "")
        if ctype.startswith("text/event-stream"):
            messages = list(_parse_sse(resp.text))
            for m in messages:
                if want_id is None or m.get("id") == want_id:
                    if "result" in m or "error" in m:
                        return m
            raise McpUnavailable("Swiggy MCP stream ended without an answer")
        try:
            body = resp.json()
        except ValueError as e:
            raise McpUnavailable("Swiggy MCP returned a body that is not JSON") from e
        if isinstance(body, list):  # a batch: pick the answer to our request
            body = next((m for m in body if want_id is None or m.get("id") == want_id), {})
        return body

    @staticmethod
    def _result_or_raise(message: dict) -> dict:
        err = message.get("error")
        if err:
            if err.get("code") == AUTH_ERROR_CODE:
                raise McpAuthError("Swiggy rejected the access token (-32001)")
            raise McpToolError(str(err.get("message", "Swiggy returned an error")), err.get("code"))
        if "result" not in message:
            raise McpUnavailable("Swiggy MCP answer had neither result nor error")
        return message["result"]

    @staticmethod
    def _unwrap(result: dict) -> Any:
        texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
        if result.get("isError"):
            raise McpToolError(" ".join(texts) or "Tool call failed")
        if result.get("structuredContent") is not None:
            return result["structuredContent"]
        joined = "\n".join(texts)
        try:
            return json.loads(joined)
        except ValueError:
            return joined


class _SessionExpired(Exception):
    pass


def _retry_after(resp: httpx.Response) -> float:
    try:
        return max(0.0, min(float(resp.headers.get("retry-after", "1")), 30.0))
    except ValueError:
        return 1.0


def _parse_sse(text: str):
    """Yields the JSON payload of each server-sent event."""
    data: list[str] = []
    for line in text.splitlines() + [""]:
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif line == "" and data:
            try:
                yield json.loads("\n".join(data))
            except ValueError:
                pass
            data = []
