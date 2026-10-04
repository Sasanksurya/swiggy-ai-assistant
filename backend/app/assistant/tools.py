"""Tool-calling layer between the graph and SwiggyPlatform.

Rules: only methods listed in CAPABILITIES can be called; a capability the platform does not
declare is NOT called and yields `unsupported_capability`; every call is logged.
"""
from __future__ import annotations

from pydantic import BaseModel

from ..platform.base import CAPABILITIES, PlatformResult, SwiggyPlatform, unsupported

_SESSION_TOOLS = {"get_cart", "add_to_cart", "update_cart", "remove_from_cart", "place_order"}


class ToolCallLog(BaseModel):
    name: str
    args: dict
    ok: bool
    error_code: str | None = None


class ToolRunner:
    def __init__(self, platform: SwiggyPlatform, session_id: str):
        self._p = platform
        self._sid = session_id
        self.calls: list[ToolCallLog] = []

    async def call(self, name: str, **args) -> PlatformResult:
        if name not in CAPABILITIES:
            raise ValueError(f"Unknown tool '{name}'; only platform capabilities can be called")
        if not self._p.capabilities().get(name, False):
            result = unsupported(self._p.source, name, self._p.unsupported_reason())
        else:
            if name in _SESSION_TOOLS:
                args = {**args, "session_id": self._sid}
            result = await getattr(self._p, name)(**args)
        self.calls.append(ToolCallLog(name=name, args=args, ok=result.ok,
                                      error_code=result.error.code if result.error else None))
        return result
