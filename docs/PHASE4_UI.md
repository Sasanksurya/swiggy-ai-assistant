# Phase 4: Chat UI with voice

## Screens
- **Conversation:** Sarah's replies are plain text; yours are bubbles. Restaurants, dishes and meal options are
  rows with actions ("See menu", "Add", "Switch to this") that send the same position-based phrases the
  backend already understands ("show the menu of number 2", "add number 1", "use option 2").
- **Order slip:** a receipt on the right (collapsible bar on phones) built only from the backend's cart
  (items, delivery, total) with a budget meter ("₹490 of ₹500. ₹10 left", or "₹40 over budget").
- **Honesty:** a demo-data banner from `/api/platform/info`, a "demo" tag on synthetic restaurants, and a
  note that Sarah can fill the order but cannot place it.

## Code map (frontend/src)
| Path | Role |
|---|---|
| lib/types.ts, lib/api.ts | Typed contract, runtime response guard, friendly errors for both backend error shapes |
| app/api/[...path]/route.ts | Same-origin proxy, runtime `BACKEND_URL`, allow-list (chat, platform), 502 when backend is down |
| hooks/useChat.ts | Messages, session, retry, reset, live cart/plan/budget derived from responses |
| lib/speech.ts | Reply -> speakable text; mic error messages; voice choice (Indian English first) |
| hooks/useSpeechRecognition.ts, useSpeechSynthesis.ts | Browser speech APIs behind feature detection |
| components/ChatApp.tsx, Cards.tsx, Slip.tsx | The interface |

## Verified
80 frontend tests (real backend responses are used as fixtures), 184 backend tests, strict typecheck, lint,
production build, and a live run of all three servers over HTTP, including the Docker image layout with a
runtime `BACKEND_URL`.

## Not verified here
The Dockerfile build itself and the microphone in a real browser (no Docker or browser in the build sandbox).
Speech is tested with fake recognition and synthesis objects.

## Backend patch
`backend-patch/budget-in-plan-cards.patch` adds `budget_inr` and `people` to plan cards so the meter survives
multi-turn requests. The UI also works without it (it falls back to what the user said on that turn).
Apply from the repo root: `git apply backend-patch/budget-in-plan-cards.patch`
