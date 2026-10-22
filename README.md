# Swiggy AI Food Assistant

[![CI](https://github.com/Sasanksurya/swiggy-ai-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Sasanksurya/swiggy-ai-assistant/actions/workflows/ci.yml)

**Stack:** FastAPI · LangGraph · LangSmith · Redis · Next.js 16 / React 19 · Web Speech API · Docker · GitHub Actions

**System design:** see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (architecture, request flow, agent graph, design decisions).

AI food-ordering assistant (chat + voice) designed to integrate with the official Swiggy Developer
Platform through authorized mechanisms. Development is zero-cost: everything runs locally.

## Status
Phase 1 (done): FastAPI backend, config (`development|staging|production`), `SwiggyPlatform`
abstraction, Mock Swiggy MCP (synthetic data), docker-compose (Postgres, Redis), tests.

Phase 2 (done): LangGraph assistant (intent detection, tool calling, restaurant/menu search, cart
operations, conversational state in memory/Redis). See docs/PHASE2.md. `POST /api/chat`.

Phase 3a (done): **Sarah** persona + budget engine ("biryani for two under 500" -> best restaurant -> cart).
See docs/PHASE3_SARAH.md.

Phase 4 (done): Next.js chat UI with voice (speech-to-text / text-to-speech). See docs/PHASE4_UI.md.

Step A (done): confirmation-gated checkout (simulated in the mock). See docs/STEP_A_CHECKOUT.md.

Phase 5 (done): GitHub Actions CI (ruff + pytest, ESLint + tsc + vitest + build, Docker image builds),
LangSmith tracing, system-design docs.

Not built yet: Google OAuth 2.0 + JWT on checkout, Kubernetes manifests, real Swiggy integration
(Stage 2, from Swiggy's current official docs).

## Run
    cp .env.example .env
    make up                    # backend :8000, mock MCP :8100
    curl localhost:8000/api/platform/info

## Test
    cd backend && pip install -r requirements-dev.txt && python -m pytest -q   # 189 tests
    cd frontend && npm ci && npm test                                          # 80 tests

CI runs the same checks on every push and pull request: `.github/workflows/ci.yml`.

## Observability (LangSmith)
1. Create a free account at https://smith.langchain.com and an API key (Settings -> API Keys).
2. In your local `.env` (never in Git): `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY=<your key>`.
3. Restart the backend and send a chat message. Each turn appears in project `swiggy-ai-assistant` as a
   `sarah_chat_turn` trace with every graph node and platform tool call as child runs, tagged by `session_id`.

## Design rules
- `MOCK_MODE=true` -> Mock MCP; `false` -> `RealSwiggyPlatform` (currently reports
  `unsupported_capability` for everything; no endpoints or tools are invented).
- Production refuses to start with `MOCK_MODE=true`.
- Every mock response carries `synthetic: true`; the UI must show the banner from `/api/platform/info`.
- Agents and business logic depend only on `app/platform/base.py`.
- No secrets in Git; `.env` is ignored.
