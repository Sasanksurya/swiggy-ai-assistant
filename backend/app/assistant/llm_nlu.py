"""Optional LLM-backed NLU (Ollama). Rules run first; the LLM only handles messages the rules
could not classify. The LLM returns structured JSON validated against NLUResult, and can only
choose from the fixed intent list, so it cannot invoke tools or invent capabilities.
"""
from __future__ import annotations

import json
import logging

import httpx
from pydantic import ValidationError

from .nlu import INTENTS, NLU, NLUResult, RuleBasedNLU

log = logging.getLogger(__name__)

_SYSTEM = (
    "You classify messages sent to a food-ordering assistant. Reply with ONE JSON object only, keys: "
    f"intent (one of {list(INTENTS)}), query (dish/cuisine/restaurant text or null), quantity (int or null), "
    "max_price (int rupees or null), veg (true/false/null), ref_index (1-based int, -1 for last, or null), "
    "order_id (string or null). Use intent 'unknown' if unsure. Never invent restaurants, dishes or prices."
)


class OllamaNLU(NLU):
    def __init__(self, base_url: str, model: str, fallback: NLU | None = None,
                 client: httpx.AsyncClient | None = None, timeout: float = 20.0):
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._rules = fallback or RuleBasedNLU()
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def parse(self, message: str, *, has_pending: bool = False) -> NLUResult:
        base = await self._rules.parse(message, has_pending=has_pending)
        if base.intent != "unknown":
            return base
        try:
            resp = await self._client.post(self._url, json={
                "model": self._model, "stream": False, "format": "json",
                "options": {"temperature": 0},
                "messages": [{"role": "system", "content": _SYSTEM},
                             {"role": "user", "content": message[:500]}]})
            resp.raise_for_status()
            data = json.loads(resp.json()["message"]["content"])
            r = NLUResult.model_validate({k: data.get(k) for k in NLUResult.model_fields if k in data})
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ValidationError) as e:
            log.warning("LLM NLU failed (%s); using rule-based result", type(e).__name__)
            return base
        if r.intent == "unknown":
            return base
        if r.query:
            r.query = r.query.strip()[:80] or None
        r.confidence = 0.7
        return r
