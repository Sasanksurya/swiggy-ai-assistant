# Step A: confirmation-gated checkout (overlay)

Contains ONLY the files that changed or are new. Extract into your repo root (D:\swiggy-ai-assistant) and
choose "Replace" when asked. Your requirements files and .env are not in this zip, so your pins are untouched.

After extracting:
1. Backend:   cd backend && python -m pytest -q          -> expect 184 passed
2. Frontend:  cd frontend && npm test                    -> expect 80 passed
3. Run mock service, backend, then `npm run dev` as before, and try:
     "Hey Sarah, biryani for two, budget around 500"  ->  "checkout"  ->  pick an address  ->  "yes"
   The confirmation card has Yes / No buttons; voice works too ("yes please").
4. git add . ; git commit -m "Confirmation-gated checkout (simulated in the mock)" ; git push

Everything is simulated in the mock: no real order is ever placed. See docs/STEP_A_CHECKOUT.md.
