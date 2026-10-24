"""Storage for the Swiggy OAuth client registration and tokens.

Tokens are secrets. They are never logged, never part of a repr, and the file is written with mode 0600
through an atomic replace so a crash cannot leave a half-written file.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class TokenSet:
    access_token: str = field(repr=False)
    refresh_token: str = field(default="", repr=False)  # empty: Swiggy sent none, so no silent renewal
    expires_at: float = 0.0  # epoch seconds
    scope: str = ""

    def seconds_left(self, now: float | None = None) -> float:
        return self.expires_at - (time.time() if now is None else now)

    @classmethod
    def from_response(cls, body: dict, now: float | None = None, keep_refresh_token: str = "") -> TokenSet:
        """A response may omit refresh_token (OAuth allows it); then the previous one, if any, stays valid.
        Raises ValueError if the response has no usable access token or lifetime."""
        now = time.time() if now is None else now
        try:
            access, lifetime = str(body["access_token"]), float(body["expires_in"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError("token response is missing access_token or expires_in") from e
        if not access:
            raise ValueError("token response has an empty access_token")
        return cls(access_token=access, refresh_token=str(body.get("refresh_token") or keep_refresh_token),
                   expires_at=now + lifetime, scope=str(body.get("scope", "")))


@dataclass
class ClientRegistration:
    """Result of dynamic client registration. Valid only for the server and redirect URI it was made for."""
    client_id: str
    base_url: str
    redirect_uri: str


@dataclass
class StoredAuth:
    registration: ClientRegistration | None = None
    tokens: TokenSet | None = None


class TokenStore(Protocol):
    def load(self) -> StoredAuth: ...
    def save(self, auth: StoredAuth) -> None: ...


class MemoryTokenStore:
    def __init__(self) -> None:
        self._auth = StoredAuth()

    def load(self) -> StoredAuth:
        return StoredAuth(self._auth.registration, self._auth.tokens)

    def save(self, auth: StoredAuth) -> None:
        self._auth = StoredAuth(auth.registration, auth.tokens)


class FileTokenStore:
    def __init__(self, path: str | Path):
        self._path = Path(path).expanduser()

    def load(self) -> StoredAuth:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            reg = raw.get("registration")
            tok = raw.get("tokens")
            return StoredAuth(ClientRegistration(**reg) if reg else None, TokenSet(**tok) if tok else None)
        except (FileNotFoundError, ValueError, TypeError, KeyError):
            return StoredAuth()  # missing or unreadable file means "not connected"

    def save(self, auth: StoredAuth) -> None:
        data = {
            "registration": auth.registration.__dict__ if auth.registration else None,
            "tokens": auth.tokens.__dict__ if auth.tokens else None,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".swiggy-tokens-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
