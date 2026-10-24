# Agent evaluation

Unit tests check functions. The evaluation suite checks **conversations**: it talks to Sarah the way a user
would and scores what she does. It runs in CI on every push, so a change that makes Sarah worse fails the build.

```
cd backend
python -m evals.run                        # scoreboard + failures
python -m evals.run --out ../docs/EVAL_REPORT.md
```

Latest report: [EVAL_REPORT.md](EVAL_REPORT.md).

## What is scored

The conversations are in `backend/evals/cases.yaml`. Each one runs on a fresh mock platform (synthetic data),
using the same `AssistantService` the API uses.

| Metric | What it checks | Gate |
|---|---|---|
| Intent accuracy | Sarah understood what the user asked for | at least 90% |
| Tool-use accuracy | she called the right platform tools, and not the forbidden ones | at least 90% |
| Reply checks | the reply says what it must, and not what it must not | at least 90% |
| Grounded replies | **every turn**: each rupee amount, restaurant name and order id in the reply came from a tool result or from the user | 100% |
| Order safety | **every turn**: `place_order` runs only after a "yes" to a confirmation question, and no reply claims an order that was not created | 100% |
| Cases fully passing | conversations with no failed check | at least 90% |

Grounding and order safety are checked automatically on every turn of every case, not only where a case asks
for it, so a new feature that invents a price or skips the confirmation fails CI even if nobody wrote a case
for it. Both have to be perfect: a food-ordering agent that makes up a price or orders without a yes is broken,
however good its other scores are.

The checks are deterministic (no LLM judge), so the suite is free, takes about a second, and gives the same
score on every run.

## Proof the checks work

The checks were tested by breaking Sarah on purpose:
- letting a stray "yes" place an order dropped **order safety to 98.2%** and failed the gate;
- showing a subtotal ₹10 lower than the cart dropped **grounding to 77.8%** and failed the gate.

`backend/tests/test_evals.py` keeps the checker honest: it must accept facts that come from tools and flag
invented amounts, names and order ids.

## What the first run found

The first baseline scored **78.8% of conversations passing** (grounding 98.1%, reply checks 88.4%). The failures
were real problems, and fixing them brought every metric to 100%:

| Found by the eval | Fix |
|---|---|
| "book a table for 4" was treated as a meal plan and Sarah asked for a budget | dine-out and table bookings are recognised as out of scope |
| "show restaurants under 300 for two" started a meal plan instead of a search | restaurant searches with a price for two stay searches |
| "show the menu of the first one" after a dish list did nothing | it opens the menu of that dish's restaurant |
| a cart over the ₹1000 cap went all the way to the address question before being refused | the cap is checked at the start of checkout |
| "biriyani" (typo) found nothing | one retry with the closest real dish word, and Sarah says what she searched for |
| the cancel reply quoted a customer-care phone number that no tool returned and could not be verified | Sarah points to Help in the Swiggy app instead; the case now forbids phone numbers |

## Cases from real use

The `voice` cases come from real speech-to-text output. "Sara order for me ne biryani for 2 members with any
budget of 500" failed because the dish search kept "sara ne biryani". Sarah now ignores her own name and common
Hindi/Hinglish filler words ("ne", "mein", "mujhe ... chahiye"), and if a dish search still finds nothing she
retries once with only the words that match real dishes.

## Limits

- The cases run on synthetic mock data, so they test Sarah's behaviour, not Swiggy's live data.
- The NLU is rule-based; the cases cover the phrasings in the file, not every way a user can say something.
- Adding a case: add a block to `cases.yaml`, run `python -m evals.run`, and commit the updated report.
