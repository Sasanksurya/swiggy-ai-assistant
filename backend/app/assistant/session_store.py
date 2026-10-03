from __future__ import annotations

from abc import ABC, abstractmethod

from .state import ConversationState

_PREFIX = "swiggy:session:"


class SessionStore(ABC):
    @abstractmethod
    async def get(self, session_id: str) -> ConversationState: ...

    @abstractmethod
    async def save(self, state: ConversationState) -> None: ...

    @abstractmethod
    async def delete(self, session_id: str) -> None: ...


class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, session_id: str) -> ConversationState:
        raw = self._data.get(session_id)
        return ConversationState.model_validate_json(raw) if raw else ConversationState(session_id=session_id)

    async def save(self, state: ConversationState) -> None:
        self._data[state.session_id] = state.model_dump_json()

    async def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)


class RedisSessionStore(SessionStore):
    def __init__(self, redis_client, ttl_seconds: int = 3600) -> None:
        self._r = redis_client
        self._ttl = ttl_seconds

    async def get(self, session_id: str) -> ConversationState:
        raw = await self._r.get(_PREFIX + session_id)
        return ConversationState.model_validate_json(raw) if raw else ConversationState(session_id=session_id)

    async def save(self, state: ConversationState) -> None:
        await self._r.set(_PREFIX + state.session_id, state.model_dump_json(), ex=self._ttl)

    async def delete(self, session_id: str) -> None:
        await self._r.delete(_PREFIX + session_id)
