# Sarah web app

Next.js (App Router, TypeScript) chat UI for the Sarah assistant, with voice input and spoken replies.

## Run (development)
    # terminal 1: mock Swiggy        cd mock-mcp && python -m uvicorn mock_swiggy_mcp.app:app --port 8100
    # terminal 2: backend            cd backend  && python -m uvicorn app.main:app --port 8000
    # terminal 3: this app
    cd frontend
    npm install
    npm run dev          # http://localhost:3000

The browser only talks to this app. `src/app/api/[...path]/route.ts` forwards `/api/chat/**` and
`/api/platform/**` to the backend at `BACKEND_URL` (default `http://localhost:8000`, read at request time).

## Scripts
| Command | What it does |
|---|---|
| `npm test` | 80 unit and component tests (Vitest + Testing Library) |
| `npm run typecheck` | TypeScript, strict |
| `npm run lint` | ESLint (React 19 rules) |
| `npm run build` / `npm start` | Production build / server |

## Voice
- **Talk:** tap the mic, speak, and the transcript is sent automatically. Saying "Hey Sarah" is optional; the
  backend ignores it. This is tap-to-talk, not an always-on wake word.
- **Replies:** spoken after voice requests, or for every reply with "Read replies aloud". Text is rewritten for
  speech first (rupees spelled out, no symbols).
- **Browsers:** Chrome and Edge work best. Safari support is partial and Firefox has no speech recognition (the
  mic is disabled with an explanation and typing still works).
- **Privacy:** in Chrome and Edge, speech recognition is performed by the browser vendor's online service.
- **Secure context:** the mic works on `http://localhost`; any other address needs HTTPS.

## Docker
From the repo root: `docker compose -f docker-compose.yml -f docker-compose.frontend.yml up --build`
