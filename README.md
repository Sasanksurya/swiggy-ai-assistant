# Swiggy AI Food Assistant

AI food-ordering assistant (chat + voice) designed to integrate with the official Swiggy Developer
Platform through authorized mechanisms. Development is zero-cost: everything runs locally.

## Status
Phase 1 (done): FastAPI backend, config (`development|staging|production`), `SwiggyPlatform`
abstraction, Mock Swiggy MCP (synthetic data), docker-compose (Postgres, Redis), tests.

Not built yet: query/intent agents, LangGraph workflow, budget engine, recommendations,
Next.js chat UI, voice, Kubernetes manifests (`k8s/`), Jenkinsfile (`jenkins/`),
real Swiggy OAuth/MCP integration (Stage 2, from Swiggy's current official docs).

## Run
    cp .env.example .env
    make up                    # backend :8000, mock MCP :8100
    curl localhost:8000/api/platform/info

## Test
    cd backend && pip install -r requirements-dev.txt && python -m pytest -q

## Design rules
- `MOCK_MODE=true` -> Mock MCP; `false` -> `RealSwiggyPlatform` (currently reports
  `unsupported_capability` for everything; no endpoints or tools are invented).
- Production refuses to start with `MOCK_MODE=true`.
- Every mock response carries `synthetic: true`; the UI must show the banner from `/api/platform/info`.
- Agents and business logic depend only on `app/platform/base.py`.
- No secrets in Git; `.env` is ignored.
