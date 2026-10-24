from app.config import Settings
from app.platform.base import CAPABILITIES
from app.platform.factory import build_platform
from app.platform.real_platform import RealSwiggyPlatform

_ARGS = {"get_restaurant_details": {"restaurant_id": "x"}, "get_menu": {"restaurant_id": "x"},
         "get_item_details": {"item_id": "x"}, "add_to_cart": {"item_id": "x"},
         "update_cart": {"item_id": "x", "quantity": 1}, "remove_from_cart": {"item_id": "x"},
         "get_order_status": {"order_id": "x"}, "get_order_details": {"order_id": "x"},
         "place_order": {"address_id": "x"}}


async def test_real_platform_never_returns_fake_data():
    p = RealSwiggyPlatform()
    assert not any(p.capabilities().values())
    for name in CAPABILITIES:
        fn = getattr(p, name)
        r = await fn(**_ARGS.get(name, {}))
        assert not r.ok and r.data is None and r.error.code == "unsupported_capability"
        assert r.source == "swiggy" and r.synthetic is False


def test_factory_switches_on_mock_mode():
    assert build_platform(Settings(_env_file=None, mock_mode=True)).source == "mock"
    assert build_platform(Settings(_env_file=None, mock_mode=False)).source == "swiggy"
