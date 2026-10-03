from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from ..assistant.factory import get_assistant
from ..assistant.service import AssistantService, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["assistant"])

_SID = Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, a: AssistantService = Depends(get_assistant)):
    return await a.chat(req.message.strip(), req.session_id)


@router.get("/{session_id}/history")
async def history(session_id: str = _SID, a: AssistantService = Depends(get_assistant)):
    return {"session_id": session_id, "history": await a.history(session_id)}


@router.delete("/{session_id}", status_code=204)
async def reset(session_id: str = _SID, a: AssistantService = Depends(get_assistant)):
    await a.reset(session_id)
