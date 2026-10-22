import os

import pytest

from app.config import Settings
from app.observability import configure_tracing


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_ENDPOINT"):
        monkeypatch.delenv(k, raising=False)


def test_tracing_off_by_default():
    assert configure_tracing(Settings(_env_file=None)) is False
    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert "LANGSMITH_API_KEY" not in os.environ


def test_tracing_needs_api_key():
    assert configure_tracing(Settings(_env_file=None, langsmith_tracing=True)) is False
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_tracing_on_exports_env():
    s = Settings(_env_file=None, langsmith_tracing=True, langsmith_api_key="lsv2_test", langsmith_project="demo")
    assert configure_tracing(s) is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "lsv2_test"
    assert os.environ["LANGSMITH_PROJECT"] == "demo"


def test_api_key_hidden_in_repr():
    s = Settings(_env_file=None, langsmith_api_key="lsv2_secret")
    assert "lsv2_secret" not in repr(s)


async def test_tool_calls_still_logged_with_tracing_off(assistant):
    r = await assistant.chat("show me biryani")
    assert r.tool_calls and all(c.ok for c in r.tool_calls)
