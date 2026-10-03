import json

import httpx

from app.assistant.factory import build_nlu
from app.assistant.llm_nlu import OllamaNLU
from app.assistant.nlu import RuleBasedNLU
from app.config import Settings

GIBBERISH = "asdf qwerty zxcv lkj poiu mnb"


def make(handler):
    calls = []

    def wrapped(request: httpx.Request):
        calls.append(json.loads(request.content))
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    return OllamaNLU("http://ollama:11434", "test-model", client=client), calls


def reply(obj_or_text):
    text = obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text)
    return httpx.Response(200, json={"message": {"role": "assistant", "content": text}})


async def test_llm_not_called_when_rules_understand():
    nlu, calls = make(lambda r: reply({"intent": "greet"}))
    assert (await nlu.parse("add 2 masala dosa")).intent == "add_to_cart"
    assert calls == []


async def test_llm_used_for_unknown_and_validated():
    nlu, calls = make(lambda r: reply({"intent": "search_menu", "query": "  spicy noodles  ",
                                       "max_price": 200, "veg": True, "extra": "ignored"}))
    r = await nlu.parse(GIBBERISH)
    assert (r.intent, r.query, r.max_price, r.veg) == ("search_menu", "spicy noodles", 200, True)
    assert calls[0]["model"] == "test-model" and calls[0]["format"] == "json" and calls[0]["stream"] is False


async def test_invalid_intent_falls_back():
    nlu, _ = make(lambda r: reply({"intent": "delete_all_orders"}))
    assert (await nlu.parse(GIBBERISH)).intent == "unknown"


async def test_bad_json_and_http_errors_fall_back():
    for h in (lambda r: reply("not json"), lambda r: httpx.Response(500),
              lambda r: httpx.Response(200, json={"oops": 1}),
              lambda r: reply({"intent": "add_to_cart", "quantity": "lots"})):
        nlu, _ = make(h)
        assert (await nlu.parse(GIBBERISH)).intent == "unknown"


async def test_connection_error_falls_back():
    def boom(request):
        raise httpx.ConnectError("down")
    nlu, _ = make(boom)
    assert (await nlu.parse(GIBBERISH)).intent == "unknown"


async def test_llm_output_cannot_trigger_unknown_tools(assistant):
    """Even a hostile LLM answer only selects an intent; the graph decides which tools run."""
    from app.assistant.service import AssistantService
    from app.assistant.session_store import InMemorySessionStore
    nlu, _ = make(lambda r: reply({"intent": "unsupported_action"}))
    a = AssistantService(assistant._platform, nlu, InMemorySessionStore())
    r = await a.chat(GIBBERISH, "s")
    assert r.intent == "unsupported_action" and r.tool_calls == []


def test_factory_selects_provider():
    assert isinstance(build_nlu(Settings(_env_file=None)), RuleBasedNLU)
    assert isinstance(build_nlu(Settings(_env_file=None, nlu_provider="ollama")), OllamaNLU)
