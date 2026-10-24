"""OAuth 2.1 + PKCE (S256) against the Swiggy MCP authorization server.

Follows https://mcp.swiggy.com/builders/docs/start/authenticate/ :
  POST /auth/register   dynamic client registration (RFC 7591), no manual client id
  GET  /auth/authorize  user signs in with phone + OTP in the browser, then returns to our redirect URI
  POST /auth/token      JSON body; exchanges the code, and refreshes (refresh tokens ROTATE)
  POST /auth/logout     revokes the session
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
import time
from collections.abc import Callable
from urllib.parse import urlencode

import httpx

from .token_store import ClientRegistration, StoredAuth, TokenSet, TokenStore

log = logging.getLogger(__name__)

SCOPE = "mcp:tools"
REFRESH_MARGIN_SECONDS = 60  # refresh when this close to expiry; an expired token cannot be refreshed
PENDING_TTL_SECONDS = 600


class OAuthError(Exception):
    """The authorization server rejected a request or could not be reached."""

    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code  # the server's `error` value, for example invalid_grant


class NotConnected(Exception):
    """No usable Swiggy session. The user has to sign in again."""


def make_pkce() -> tuple[str, str]:
    """Returns (verifier, S256 challenge)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class SwiggyOAuth:
    def __init__(self, base_url: str, redirect_uri: str, store: TokenStore,
                 client: httpx.AsyncClient | None = None, clock: Callable[[], float] = time.time):
        self.base_url = base_url.rstrip("/")
        self.redirect_uri = redirect_uri
        self._store = store
        self._http = client or httpx.AsyncClient(timeout=15.0, follow_redirects=False)
        self._clock = clock
        self._pending: dict[str, tuple[str, float]] = {}  # state -> (verifier, created_at)
        self._refresh_lock = asyncio.Lock()

    # ----- status -----
    def is_connected(self) -> bool:
        return self._store.load().tokens is not None

    def status(self) -> dict:
        t = self._store.load().tokens
        return {"connected": t is not None, "expires_in_seconds": int(t.seconds_left(self._clock())) if t else None,
                "base_url": self.base_url, "redirect_uri": self.redirect_uri}

    # ----- step 1: register once, then send the user to Swiggy -----
    async def _registration(self) -> ClientRegistration:
        auth = self._store.load()
        reg = auth.registration
        if reg and reg.base_url == self.base_url and reg.redirect_uri == self.redirect_uri:
            return reg
        resp = await self._post("/auth/register", {
            "client_name": "Swiggy AI Food Assistant",
            "redirect_uris": [self.redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPE,
        })
        client_id = resp.get("client_id")
        if not client_id:
            raise OAuthError("Client registration returned no client_id")
        reg = ClientRegistration(client_id=client_id, base_url=self.base_url, redirect_uri=self.redirect_uri)
        self._store.save(StoredAuth(reg, auth.tokens))
        return reg

    async def begin(self) -> str:
        """Returns the URL to open in the browser. Remembers the PKCE verifier for the callback."""
        reg = await self._registration()
        verifier, challenge = make_pkce()
        state = secrets.token_urlsafe(24)
        now = self._clock()
        self._pending = {s: v for s, v in self._pending.items() if now - v[1] < PENDING_TTL_SECONDS}
        self._pending[state] = (verifier, now)
        query = urlencode({"response_type": "code", "client_id": reg.client_id, "redirect_uri": self.redirect_uri,
                           "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
                           "scope": SCOPE})
        return f"{self.base_url}/auth/authorize?{query}"

    # ----- step 2: the browser comes back with ?code=&state= -----
    async def complete(self, code: str, state: str) -> None:
        entry = self._pending.pop(state, None)  # single use: a replayed callback finds nothing
        if not entry or self._clock() - entry[1] > PENDING_TTL_SECONDS:
            raise OAuthError("Unknown or expired sign-in attempt. Start again from /api/swiggy/connect.")
        body = await self._post("/auth/token", {"grant_type": "authorization_code", "code": code,
                                                "code_verifier": entry[0], "redirect_uri": self.redirect_uri})
        auth = self._store.load()
        previous = auth.tokens.refresh_token if auth.tokens else ""
        try:
            tokens = TokenSet.from_response(body, self._clock(), keep_refresh_token=previous)
        except ValueError as e:
            raise OAuthError("Swiggy sent an unexpected token response.", "invalid_response") from e
        self._store.save(StoredAuth(auth.registration, tokens))
        log.info("Swiggy account connected (refresh token %s)", "received" if tokens.refresh_token else "NOT sent")

    # ----- tokens for API calls -----
    async def get_access_token(self) -> str:
        tokens = self._store.load().tokens
        if tokens is None:
            raise NotConnected("Swiggy account is not connected.")
        if tokens.seconds_left(self._clock()) <= REFRESH_MARGIN_SECONDS:
            tokens = await self.refresh(only_if_older_than=tokens)
        return tokens.access_token

    async def refresh(self, only_if_older_than: TokenSet | None = None) -> TokenSet:
        """Refresh tokens. The refresh token rotates, so two refreshes at once would invalidate each other;
        the lock plus the re-check below make sure only one runs."""
        async with self._refresh_lock:
            auth = self._store.load()
            current = auth.tokens
            if current is None:
                raise NotConnected("Swiggy account is not connected.")
            if only_if_older_than is not None and current.refresh_token != only_if_older_than.refresh_token:
                return current  # someone else already refreshed while we waited
            if not current.refresh_token:  # Swiggy gave none at sign-in: the session ends when the access token does
                self._store.save(StoredAuth(auth.registration, None))
                raise NotConnected("Swiggy session expired. Please connect again.")
            try:
                body = await self._post("/auth/token", {"grant_type": "refresh_token",
                                                        "refresh_token": current.refresh_token})
            except OAuthError as e:
                if e.code in {"invalid_grant", "invalid_request"}:
                    self._store.save(StoredAuth(auth.registration, None))  # dead session: sign in again
                    raise NotConnected("Swiggy session expired. Please connect again.") from e
                raise
            try:
                fresh = TokenSet.from_response(body, self._clock(), keep_refresh_token=current.refresh_token)
            except ValueError as e:
                raise OAuthError("Swiggy sent an unexpected token response.", "invalid_response") from e
            self._store.save(StoredAuth(auth.registration, fresh))
            return fresh

    async def disconnect(self) -> None:
        auth = self._store.load()
        if auth.tokens:  # best effort: always forget locally even if Swiggy cannot be reached
            try:
                await self._http.post(f"{self.base_url}/auth/logout",
                                      headers={"Authorization": f"Bearer {auth.tokens.access_token}"})
            except httpx.HTTPError:
                log.warning("Could not reach Swiggy to revoke the session; token forgotten locally")
        self._store.save(StoredAuth(auth.registration, None))

    # ----- http -----
    async def _post(self, path: str, body: dict) -> dict:
        try:
            resp = await self._http.post(f"{self.base_url}{path}", json=body)
        except httpx.HTTPError as e:
            raise OAuthError(f"Swiggy authorization server unreachable ({type(e).__name__})") from e
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400:
            raise OAuthError(f"{path} failed with {resp.status_code}: "
                             f"{data.get('error', 'error')} {data.get('error_description', '')}".strip(),
                             code=str(data.get("error", "")))
        return data
