import asyncio
import base64
import hashlib
import os
import stat
from urllib.parse import parse_qs, urlparse

import pytest

from app.platform.swiggy.oauth import NotConnected, OAuthError, make_pkce
from app.platform.swiggy.token_store import FileTokenStore, StoredAuth, TokenSet


def test_pkce_challenge_is_s256_of_verifier():
    verifier, challenge = make_pkce()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected and "=" not in verifier and len(verifier) >= 43


async def test_begin_registers_once_and_builds_authorize_url(oauth, fake_swiggy):
    url1 = await oauth.begin()
    url2 = await oauth.begin()
    assert fake_swiggy.registrations == 1
    q = parse_qs(urlparse(url1).query)
    assert urlparse(url1).path == "/auth/authorize"
    assert q["response_type"] == ["code"] and q["code_challenge_method"] == ["S256"]
    assert q["scope"] == ["mcp:tools"] and q["redirect_uri"] == ["http://localhost:8000/api/swiggy/callback"]
    assert q["state"] != parse_qs(urlparse(url2).query)["state"]  # fresh state and challenge every time


async def test_full_login_stores_tokens_and_sends_documented_body(connected, fake_swiggy):
    assert connected.is_connected()
    body = fake_swiggy.token_requests[0]
    assert set(body) == {"grant_type", "code", "code_verifier", "redirect_uri"}
    st = connected.status()
    assert st["connected"] and 400000 < st["expires_in_seconds"] <= 432000


async def test_unknown_or_replayed_state_is_rejected_before_contacting_swiggy(oauth, browser, fake_swiggy):
    with pytest.raises(OAuthError):
        await oauth.complete("whatever", "never-issued")
    assert fake_swiggy.token_requests == []
    code, state = await browser(await oauth.begin())
    await oauth.complete(code, state)
    with pytest.raises(OAuthError):  # the same callback again must not work
        await oauth.complete(code, state)
    assert len(fake_swiggy.token_requests) == 1  # our own state check stopped it, Swiggy never saw a replay


async def test_expired_sign_in_attempt_is_rejected(oauth, browser):
    now = [1000.0]
    oauth._clock = lambda: now[0]
    code, state = await browser(await oauth.begin())
    now[0] += 601
    with pytest.raises(OAuthError):
        await oauth.complete(code, state)


async def test_bad_code_is_reported_without_connecting(oauth):
    await oauth.begin()
    state = next(iter(oauth._pending))
    with pytest.raises(OAuthError) as e:
        await oauth.complete("not-a-real-code", state)
    assert e.value.code == "invalid_grant" and not oauth.is_connected()


async def test_not_connected_raises(oauth):
    with pytest.raises(NotConnected):
        await oauth.get_access_token()


async def test_refresh_rotates_and_persists(connected, fake_swiggy):
    old = connected._store.load().tokens
    fresh = await connected.refresh()
    assert fresh.refresh_token != old.refresh_token and fresh.access_token != old.access_token
    assert connected._store.load().tokens.refresh_token == fresh.refresh_token
    assert fake_swiggy.refresh[old.refresh_token] is False


async def test_access_token_refreshed_automatically_near_expiry(oauth, browser, fake_swiggy):
    fake_swiggy.expires_in = 30  # inside the 60 s safety margin
    code, state = await browser(await oauth.begin())
    await oauth.complete(code, state)
    token = await oauth.get_access_token()
    assert fake_swiggy.refresh_calls == 1 and token in fake_swiggy.access


async def test_concurrent_callers_refresh_only_once(oauth, browser, fake_swiggy):
    fake_swiggy.expires_in = 30
    code, state = await browser(await oauth.begin())
    await oauth.complete(code, state)
    tokens = await asyncio.gather(*(oauth.get_access_token() for _ in range(6)))
    assert fake_swiggy.refresh_calls == 1  # refresh tokens rotate, so a second refresh would kill the session
    assert len(set(tokens)) == 1


async def test_dead_refresh_token_means_sign_in_again(connected, fake_swiggy):
    fake_swiggy.refresh = {k: False for k in fake_swiggy.refresh}
    with pytest.raises(NotConnected):
        await connected.refresh()
    assert not connected.is_connected()
    assert connected._store.load().registration is not None  # the client registration is kept


async def test_disconnect_forgets_tokens(connected):
    await connected.disconnect()
    assert not connected.is_connected()


def test_file_store_roundtrip_is_private_and_hides_tokens(tmp_path):
    path = tmp_path / "sub" / "tokens.json"
    store = FileTokenStore(path)
    store.save(StoredAuth(None, TokenSet("secret-access", "secret-refresh", 123.0, "mcp:tools")))
    assert store.load().tokens.refresh_token == "secret-refresh"
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "secret" not in repr(store.load().tokens)
    assert FileTokenStore(tmp_path / "missing.json").load() == StoredAuth()
    path.write_text("not json")
    assert store.load() == StoredAuth()


async def test_sign_in_without_refresh_token_still_connects(oauth, browser, fake_swiggy):
    fake_swiggy.omit_refresh_token = True  # seen with the real server on a repeat sign-in
    code, state = await browser(await oauth.begin())
    await oauth.complete(code, state)
    assert oauth.is_connected()
    assert (await oauth.get_access_token()).startswith("at-")


async def test_repeat_sign_in_without_refresh_token_keeps_the_old_one(connected, browser, fake_swiggy):
    old = connected._store.load().tokens.refresh_token
    assert old
    fake_swiggy.omit_refresh_token = True
    code, state = await browser(await connected.begin())
    await connected.complete(code, state)
    assert connected._store.load().tokens.refresh_token == old


async def test_expired_session_without_refresh_token_asks_to_sign_in_again(oauth, browser, fake_swiggy):
    fake_swiggy.omit_refresh_token = True
    code, state = await browser(await oauth.begin())
    await oauth.complete(code, state)
    oauth._clock = lambda: 10**10  # far in the future: the 5 day access token has run out
    with pytest.raises(NotConnected):
        await oauth.get_access_token()
    assert fake_swiggy.refresh_calls == 0 and not oauth.is_connected()


async def test_malformed_token_response_is_a_clean_error_not_a_crash(oauth, browser, fake_swiggy):
    fake_swiggy.broken_token_body = True
    code, state = await browser(await oauth.begin())
    with pytest.raises(OAuthError):
        await oauth.complete(code, state)
    assert not oauth.is_connected()
