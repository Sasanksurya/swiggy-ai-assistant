"""Mock Swiggy MCP service. Every response is marked synthetic."""
from fastapi import FastAPI
from pydantic import BaseModel, Field

from .tools import TOOLS, ToolError

app = FastAPI(title="Mock Swiggy MCP (SYNTHETIC DATA)", version="0.1.0")


class ToolCall(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


@app.get("/health")
def health():
    return {"status": "ok", "synthetic": True}


@app.get("/tools")
def list_tools():
    return {"synthetic": True, "tools": sorted(TOOLS)}


@app.post("/tools/call")
def call_tool(call: ToolCall):
    base = {"source": "mock", "synthetic": True}
    fn = TOOLS.get(call.name)
    if fn is None:
        return {**base, "ok": False,
                "error": {"code": "unsupported_capability", "message": f"Unknown tool: {call.name}"}}
    try:
        return {**base, "ok": True, "data": fn(**call.arguments)}
    except ToolError as e:
        return {**base, "ok": False, "error": {"code": e.code, "message": e.message}}
    except TypeError as e:
        return {**base, "ok": False, "error": {"code": "invalid_argument", "message": str(e)}}
