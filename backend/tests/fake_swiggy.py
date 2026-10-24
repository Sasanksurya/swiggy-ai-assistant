"""A small fake of the Swiggy MCP authorization server and Food MCP server, for tests only.

It follows the behaviour documented at https://mcp.swiggy.com/builders/docs/ : dynamic client registration,
PKCE S256, JSON token bodies, rotating refresh tokens, Bearer-protected JSON-RPC at /food. It contains no
real Swiggy data and is never used outside tests.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

ADDRESSES = [{"addressId": "addr-1", "label": "Home", "displayText": "Test Street"}]


class FakeSwiggy:
    def __init__(self) -> None:
        self.app = FastAPI()
        self.clients: dict[str, dict] = {}
        self.codes: dict[str, dict] = {}
        self.access: dict[str, float] = {}      # access token -> valid flag (1 valid)
        self.refresh: dict[str, bool] = {}      # refresh token -> still valid
        self.sessions: set[str] = set()
        self.registrations = 0
        self.refresh_calls = 0
        self.rpc_calls: list[str] = []
        self.token_requests: list[dict] = []
        self.expires_in = 432000
        self.fail_next: list[tuple[int, dict]] = []   # queued (status, headers) failures for /food
        self.use_sse = False
        self.drop_sessions_once = False
        self._routes()

    # ----- helpers used by tests -----
    def issue_tokens(self) -> dict:
        access, refresh = "at-" + secrets.token_hex(8), "rt-" + secrets.token_hex(8)
        self.access[access] = 1
        self.refresh[refresh] = True
        return {"access_token": access, "refresh_token": refresh, "token_type": "Bearer",
                "expires_in": self.expires_in, "scope": "mcp:tools mcp:resources mcp:prompts"}

    # ----- routes -----
    def _routes(self) -> None:
        app = self.app

        @app.post("/auth/register")
        async def register(req: Request):
            body = await req.json()
            self.registrations += 1
            cid = f"client-{self.registrations}"
            self.clients[cid] = {"redirect_uris": body["redirect_uris"]}
            return JSONResponse({"client_id": cid}, status_code=201)

        @app.get("/auth/authorize")
        async def authorize(req: Request):
            q = req.query_params
            client = self.clients.get(q.get("client_id", ""))
            if (not client or q.get("redirect_uri") not in client["redirect_uris"]
                    or q.get("code_challenge_method") != "S256" or q.get("response_type") != "code"):
                return JSONResponse({"error": "invalid_request"}, status_code=400)
            code = "code-" + secrets.token_hex(6)
            self.codes[code] = {"challenge": q["code_challenge"], "redirect_uri": q["redirect_uri"]}
            return Response(status_code=302, headers={
                "location": q["redirect_uri"] + "?" + urlencode({"code": code, "state": q["state"]})})

        @app.post("/auth/token")
        async def token(req: Request):
            body = await req.json()
            self.token_requests.append(body)
            if body.get("grant_type") == "authorization_code":
                entry = self.codes.pop(body.get("code", ""), None)  # single use
                digest = hashlib.sha256(body.get("code_verifier", "").encode()).digest()
                challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
                if not entry or entry["challenge"] != challenge or entry["redirect_uri"] != body.get("redirect_uri"):
                    return JSONResponse({"error": "invalid_grant", "error_description": "bad code"}, status_code=400)
                return self.issue_tokens()
            if body.get("grant_type") == "refresh_token":
                self.refresh_calls += 1
                old = body.get("refresh_token", "")
                if not self.refresh.get(old):
                    return JSONResponse({"error": "invalid_grant", "error_description": "bad refresh"},
                                        status_code=400)
                self.refresh[old] = False  # rotation: the old refresh token dies
                fresh = self.issue_tokens()
                fresh["expires_in"] = 2592000
                return fresh
            return JSONResponse({"error": "invalid_request"}, status_code=400)

        @app.post("/auth/logout")
        async def logout(req: Request):
            return {"ok": True}

        @app.post("/food")
        async def food(req: Request):
            if self.fail_next:
                status, headers = self.fail_next.pop(0)
                return Response(status_code=status, headers=headers)
            auth = req.headers.get("authorization", "")
            if not auth.startswith("Bearer ") or not self.access.get(auth[7:]):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            msg = await req.json()
            method, rid = msg.get("method"), msg.get("id")
            self.rpc_calls.append(method)
            if method == "initialize":
                sid = secrets.token_hex(8)
                self.sessions.add(sid)
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                             "serverInfo": {"name": "fake-swiggy-food"}}},
                    headers={"mcp-session-id": sid})
            sid = req.headers.get("mcp-session-id", "")
            if sid not in self.sessions or self.drop_sessions_once:
                self.drop_sessions_once = False
                self.sessions.discard(sid)
                return Response(status_code=404)
            if method == "notifications/initialized":
                return Response(status_code=202)
            if method == "tools/list":
                return self._reply(rid, {"tools": [{"name": "get_addresses", "inputSchema": {"type": "object"}},
                                                   {"name": "place_food_order", "inputSchema": {"type": "object"}}]})
            if method == "tools/call":
                name = msg["params"]["name"]
                if name == "get_addresses":
                    return self._reply(rid, {"content": [{"type": "text", "text": json.dumps(
                        {"success": True, "data": ADDRESSES})}]})
                if name == "place_food_order":
                    return self._reply(rid, {"content": [{"type": "text", "text": json.dumps(
                        {"success": True, "data": {"orderId": "o-1"}})}]})
                if name == "tool_error":
                    return self._reply(rid, {"isError": True, "content": [{"type": "text", "text": "Restaurant closed"}]})
                if name == "auth_error":
                    return JSONResponse({"jsonrpc": "2.0", "id": rid, "error": {"code": -32001, "message": "auth"}})
                return JSONResponse({"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": "Unknown tool"}})
            return JSONResponse({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "no method"}})

    def _reply(self, rid, result: dict):
        payload = {"jsonrpc": "2.0", "id": rid, "result": result}
        if self.use_sse:
            return Response(content=f"event: message\ndata: {json.dumps(payload)}\n\n",
                            media_type="text/event-stream")
        return JSONResponse(payload)
