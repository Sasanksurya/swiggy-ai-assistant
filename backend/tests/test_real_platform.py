from app.config import Settings
from app.platform.base import CAPABILITIES
from app.platform.factory import build_platform
from app.platform.real_platform import RealSwiggyPlatform


async def test_real_platform_never_returns_fake_data():
    p = RealSwiggyPlatform()
    assert not any(p.capabilities().values())
    for name in CAPABILITIES:
        fn = getattr(p, name)
        args = {"restaurant_id": "x"} if "restaurant" in name and "search" not in name else {}
        r = await fn(**args) if args else await fn()
        assert not r.ok and r.data is None and r.error.code == "unsupported_capability"
        assert r.source == "swiggy" and r.synthetic is False


def test_factory_switches_on_mock_mode():
    assert build_platform(Settings(_env_file=None, mock_mode=True)).source == "mock"
    assert build_platform(Settings(_env_file=None, mock_mode=False)).source == "swiggy"
