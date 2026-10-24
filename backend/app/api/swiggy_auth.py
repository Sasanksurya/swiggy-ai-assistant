"""Sign in with Swiggy (OAuth 2.1 + PKCE). The user types their phone number and OTP on Swiggy's page,
never here. Disabled with SWIGGY_CONNECT_ENABLED=false for shared or public deployments, because whoever
connects decides which Swiggy account this server acts for."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from ..config import Settings, get_settings
from ..platform.swiggy.oauth import OAuthError, SwiggyOAuth
from ..platform.swiggy.runtime import get_oauth

router = APIRouter(prefix="/api/swiggy", tags=["swiggy"])

_PAGE = ("<!doctype html><meta charset=utf-8><title>Swiggy AI Food Assistant</title>"
         "<body style='font-family:system-ui;max-width:32rem;margin:4rem auto;padding:0 1rem'>{}</body>")


def _enabled(s: Settings = Depends(get_settings)) -> None:
    if not s.swiggy_connect_enabled:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/status")
async def status(s: Settings = Depends(get_settings), oauth: SwiggyOAuth = Depends(get_oauth)):
    return {**oauth.status(), "mode": "mock" if s.mock_mode else "swiggy",
            "connect_enabled": s.swiggy_connect_enabled}


@router.get("/connect", dependencies=[Depends(_enabled)])
async def connect(oauth: SwiggyOAuth = Depends(get_oauth)):
    try:
        url = await oauth.begin()
    except OAuthError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return RedirectResponse(url, status_code=302)


@router.get("/callback", dependencies=[Depends(_enabled)], response_class=HTMLResponse)
async def callback(code: str | None = Query(None, max_length=2048), state: str | None = Query(None, max_length=512),
                   error: str | None = Query(None, max_length=200), oauth: SwiggyOAuth = Depends(get_oauth)):
    if error or not code or not state:
        return HTMLResponse(_PAGE.format("<h1>Sign-in was not completed</h1>"
                                         "<p>Swiggy did not approve the sign-in. Go back and try again.</p>"),
                            status_code=400)
    try:
        await oauth.complete(code, state)
    except OAuthError:
        return HTMLResponse(_PAGE.format("<h1>Sign-in failed</h1><p>This sign-in link is no longer valid. "
                                         "Start again from <code>/api/swiggy/connect</code>.</p>"),
                            status_code=400)
    return HTMLResponse(_PAGE.format("<h1>Swiggy account connected</h1><p>You can close this tab.</p>"))


@router.post("/disconnect", dependencies=[Depends(_enabled)], status_code=204)
async def disconnect(oauth: SwiggyOAuth = Depends(get_oauth)):
    await oauth.disconnect()
