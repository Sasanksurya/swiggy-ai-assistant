from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel

from ..platform.base import SwiggyPlatform
from .graph import build_assistant_graph
from .nlu import NLU
from .session_store import SessionStore
from .tools import ToolCallLog, ToolRunner


class ChatResponse(BaseModel):
    session_id: str
    assistant_name: str
    reply: str
    intent: str
    entities: dict[str, Any]
    cards: dict[str, Any] = {}
    tool_calls: list[ToolCallLog] = []
    source: str            # "mock" | "swiggy"
    synthetic: bool        # True => data is not real Swiggy data; UI must label it


class AssistantService:
    def __init__(self, platform: SwiggyPlatform, nlu: NLU, store: SessionStore, assistant_name: str = "Sarah",
                 allow_orders: bool = True):
        self._name = assistant_name
        self._platform = platform
        self._store = store
        self._graph = build_assistant_graph(nlu, assistant_name, allow_orders)

    async def chat(self, message: str, session_id: str | None = None) -> ChatResponse:
        sid = session_id or uuid.uuid4().hex
        conv = await self._store.get(sid)
        runner = ToolRunner(self._platform, sid)
        out = await self._graph.ainvoke({"message": message, "conv": conv, "runner": runner})
        await self._store.save(out["conv"])
        n = out["nlu"]
        return ChatResponse(
            session_id=sid, assistant_name=self._name, reply=out["reply"], intent=out["intent"],
            entities=n.model_dump(exclude={"intent", "confidence"}, exclude_none=True),
            cards=out.get("cards") or {}, tool_calls=runner.calls,
            source=self._platform.source, synthetic=self._platform.source == "mock",
        )

    async def history(self, session_id: str):
        return (await self._store.get(session_id)).history

    async def reset(self, session_id: str) -> None:
        await self._store.delete(session_id)
