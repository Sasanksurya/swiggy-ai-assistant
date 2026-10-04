from __future__ import annotations

from functools import lru_cache

from ..config import Settings, get_settings
from ..platform.factory import get_platform
from .llm_nlu import OllamaNLU
from .nlu import NLU, RuleBasedNLU
from .service import AssistantService
from .session_store import InMemorySessionStore, RedisSessionStore, SessionStore


def build_nlu(settings: Settings) -> NLU:
    if settings.nlu_provider == "ollama":
        return OllamaNLU(settings.ollama_url, settings.ollama_model,
                         fallback=RuleBasedNLU(settings.assistant_name))
    return RuleBasedNLU(settings.assistant_name)


def build_store(settings: Settings) -> SessionStore:
    if settings.session_store == "redis":
        import redis.asyncio as aioredis
        return RedisSessionStore(aioredis.from_url(settings.redis_url, decode_responses=True),
                                 settings.session_ttl_seconds)
    return InMemorySessionStore()


@lru_cache
def get_assistant() -> AssistantService:
    s = get_settings()
    return AssistantService(get_platform(), build_nlu(s), build_store(s), s.assistant_name,
                            allow_orders=s.mock_mode or s.allow_real_orders)
