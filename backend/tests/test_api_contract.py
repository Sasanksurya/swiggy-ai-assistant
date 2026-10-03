"""Regression guard: Phase 1 endpoints must keep existing. New phases may ADD routes only."""
from app.main import app

PHASE1 = {
    ("DELETE", "/api/cart/items/{item_id}"), ("GET", "/api/cart"), ("GET", "/api/items/{item_id}"),
    ("GET", "/api/menu/search"), ("GET", "/api/orders/{order_id}"),
    ("GET", "/api/orders/{order_id}/status"), ("GET", "/api/platform/info"),
    ("GET", "/api/restaurants"), ("GET", "/api/restaurants/{restaurant_id}"),
    ("GET", "/api/restaurants/{restaurant_id}/menu"), ("GET", "/health"), ("GET", "/health/ready"),
    ("PATCH", "/api/cart/items/{item_id}"), ("POST", "/api/cart/items"),
}


def test_phase1_routes_still_present():
    spec = app.openapi()
    now = {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops}
    assert PHASE1 <= now, f"missing: {PHASE1 - now}"
