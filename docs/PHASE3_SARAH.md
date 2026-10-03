# Phase 3a: Sarah and the budget engine

"Hey Sarah, I'm looking for biryani at a range of 500 for two combos."

## What happens
1. NLU strips the wake phrase ("Hey Sarah") and extracts: dish, people, budget, veg, drinks.
2. If something is missing, Sarah asks for it ("How many people?", "What's your budget?"). Plain numbers
   such as "500" or "2" are understood as the answer. Changing the subject cancels the half-finished request.
3. Tools: `search_restaurants` (open restaurants, ratings, delivery time) and `search_menu` (dishes, drinks).
4. `budget.build_plans` (pure function) picks, per restaurant, the dish combination that serves everyone and
   uses the budget best (ties -> more variety). Ranking: includes requested drinks, then rating, delivery time.
5. Sarah adds the top plan to the cart, reads the REAL delivery fee from the platform's cart, and if the total
   is over budget re-plans once with `budget - fee`. If it still cannot fit, she says by how much it is over.
6. Alternatives are listed (item totals, before delivery); "use option 2" switches the cart to another plan.

## Safety rules (tested)
- Totals, fees and prices always come from tool results. The planner never assumes a delivery fee.
- A non-empty cart is never modified by planning; only an explicit "use option N" replaces it.
- Impossible budgets are explained with the cheapest real option; unknown dishes are reported as not found.
- Group size 1-8. Real mode returns "not configured", no plans, no data.
- Order placement is NOT a platform capability, so Sarah says she cannot place orders.

## Config
`ASSISTANT_NAME=Sarah` (wake phrase and replies follow this name).
