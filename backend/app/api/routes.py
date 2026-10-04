from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException

from ..config import Settings, get_settings
from ..platform.base import PlatformResult, SwiggyPlatform
from ..platform.factory import get_platform

router = APIRouter()

_STATUS = {"not_found": 404, "invalid_argument": 400, "item_unavailable": 409,
           "restaurant_conflict": 409, "empty_cart": 409, "cart_cap_exceeded": 409,
           "unsupported_capability": 501, "mcp_unavailable": 502}


def respond(result: PlatformResult) -> PlatformResult:
    if result.ok:
        return result
    code = result.error.code if result.error else "error"
    raise HTTPException(status_code=_STATUS.get(code, 400), detail=result.model_dump())


async def _tcp_ok(url: str, default_port: int) -> bool:
    u = urlparse(url)
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(u.hostname, u.port or default_port), 2)
        w.close()
        return True
    except Exception:
        return False


@router.get("/health")
async def health(s: Settings = Depends(get_settings)):
    return {"status": "ok", "env": s.app_env, "mock_mode": s.mock_mode}


@router.get("/health/ready")
async def ready(s: Settings = Depends(get_settings), p: SwiggyPlatform = Depends(get_platform)):
    checks = {"postgres": await _tcp_ok(s.database_url, 5432), "redis": await _tcp_ok(s.redis_url, 6379)}
    if s.mock_mode:
        checks["mock_mcp"] = await p._c.health()  # type: ignore[attr-defined]
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", **checks}


@router.get("/api/platform/info")
async def info(s: Settings = Depends(get_settings), p: SwiggyPlatform = Depends(get_platform)):
    return {
        "mode": "mock" if s.mock_mode else "swiggy",
        "synthetic": s.mock_mode,
        "banner": "Demo mode: all restaurants, menus and prices are synthetic, not real Swiggy data."
        if s.mock_mode else None,
        "capabilities": p.capabilities(),
    }


@router.get("/api/restaurants")
async def restaurants(query: str = "", cuisine: str | None = None, max_price_for_two_inr: int | None = None,
                      open_only: bool = False, p: SwiggyPlatform = Depends(get_platform)):
    return respond(await p.search_restaurants(query, cuisine, max_price_for_two_inr, open_only))


@router.get("/api/restaurants/{restaurant_id}")
async def restaurant(restaurant_id: str, p: SwiggyPlatform = Depends(get_platform)):
    return respond(await p.get_restaurant_details(restaurant_id))


@router.get("/api/restaurants/{restaurant_id}/menu")
async def menu(restaurant_id: str, p: SwiggyPlatform = Depends(get_platform)):
    return respond(await p.get_menu(restaurant_id))


@router.get("/api/menu/search")
async def menu_search(query: str = "", restaurant_id: str | None = None, max_price_inr: int | None = None,
                      veg_only: bool = False, p: SwiggyPlatform = Depends(get_platform)):
    return respond(await p.search_menu(query, restaurant_id, max_price_inr, veg_only))


@router.get("/api/items/{item_id}")
async def item(item_id: str, p: SwiggyPlatform = Depends(get_platform)):
    return respond(await p.get_item_details(item_id))


@router.get("/api/cart")
async def cart(x_session_id: str = Header("default"), p: SwiggyPlatform = Depends(get_platform)):
    return respond(await p.get_cart(x_session_id))


@router.post("/api/cart/items")
async def cart_add(item_id: str, quantity: int = 1, x_session_id: str = Header("default"),
                   p: SwiggyPlatform = Depends(get_platform)):
    return respond(await p.add_to_cart(item_id, quantity, x_session_id))


@router.patch("/api/cart/items/{item_id}")
async def cart_update(item_id: str, quantity: int, x_session_id: str = Header("default"),
                      p: SwiggyPlatform = Depends(get_platform)):
    return respond(await p.update_cart(item_id, quantity, x_session_id))


@router.delete("/api/cart/items/{item_id}")
async def cart_remove(item_id: str, x_session_id: str = Header("default"),
                      p: SwiggyPlatform = Depends(get_platform)):
    return respond(await p.remove_from_cart(item_id, x_session_id))


@router.get("/api/orders/{order_id}")
async def order(order_id: str, p: SwiggyPlatform = Depends(get_platform)):
    return respond(await p.get_order_details(order_id))


@router.get("/api/orders/{order_id}/status")
async def order_status(order_id: str, p: SwiggyPlatform = Depends(get_platform)):
    return respond(await p.get_order_status(order_id))
