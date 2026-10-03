import pytest
from pydantic import ValidationError

from app.config import Settings


def test_defaults_are_development_mock():
    s = Settings(_env_file=None)
    assert s.app_env == "development" and s.mock_mode is True


def test_production_requires_real_mode():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", mock_mode=True)


def test_production_with_real_mode_ok():
    assert Settings(_env_file=None, app_env="production", mock_mode=False).mock_mode is False
