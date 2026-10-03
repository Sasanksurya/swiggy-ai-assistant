# Phase 2: Assistant layer (LangGraph)

## Flow
    POST /api/chat {message, session_id?}
      -> AssistantService: load ConversationState (memory or Redis)
      -> LangGraph:  understand -> route(intent) -> <capability node> -> finalize
      -> save state, return reply + cards + tool_calls + source/synthetic flags

## Modules (backend/app/assistant)
| File | Role |
|---|---|
| state.py | ConversationState: history, last shown restaurants/items, pending clarification |
| session_store.py | InMemorySessionStore, RedisSessionStore (TTL) |
| nlu.py | `NLU` interface + RuleBasedNLU (intent + entities: query, qty, budget, veg, ordinal, order id) |
| llm_nlu.py | OllamaNLU: rules first, LLM only for "unknown"; JSON validated; falls back on any failure |
| tools.py | ToolRunner: only SwiggyPlatform capabilities, only if declared, logs every call |
| resolve.py | "the second one", "the dosa" -> concrete item/restaurant |
| graph.py | The LangGraph workflow and one node per capability |
| service.py | Orchestrates store + graph, builds ChatResponse |

## Guarantees (all covered by tests)
- Replies contain only data returned by tools. Nothing is generated or assumed.
- Checkout, payment and cancel are NOT platform capabilities -> honest refusal, zero tool calls.
- Real mode (`MOCK_MODE=false`) reports the platform's own "not configured" reason; no fabricated data.
- The LLM can only pick an intent from a fixed list; it never calls tools or sees credentials.
- Quantities are capped (1-20); session ids are validated; messages are limited to 500 chars.
- Phase 1 routes are unchanged (contract test) and share cart state with chat.

## Try it
    curl -X POST localhost:8000/api/chat -H 'content-type: application/json' \
      -d '{"message":"veg items under 100","session_id":"demo"}'
