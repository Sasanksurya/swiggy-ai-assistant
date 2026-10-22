"""LangSmith tracing setup.

LangGraph and the `traceable` tool wrapper report runs to LangSmith when the LANGSMITH_* environment
variables are set. Settings are read from `.env` by pydantic-settings, which does not export them to the
process environment, so this module copies them there once at startup.

Tracing is opt-in: with LANGSMITH_TRACING=false (the default) nothing is sent anywhere.
"""
from __future__ import annotations

import logging
import os

from .config import Settings

log = logging.getLogger(__name__)


def configure_tracing(settings: Settings) -> bool:
    """Enable LangSmith tracing if configured. Returns True when tracing is on."""
    if not settings.langsmith_tracing:
        os.environ["LANGSMITH_TRACING"] = "false"
        return False
    key = settings.langsmith_api_key.get_secret_value() if settings.langsmith_api_key else ""
    if not key:
        log.warning("LANGSMITH_TRACING=true but LANGSMITH_API_KEY is empty; tracing disabled")
        os.environ["LANGSMITH_TRACING"] = "false"
        return False
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    log.info("LangSmith tracing enabled (project=%s)", settings.langsmith_project)
    return True
