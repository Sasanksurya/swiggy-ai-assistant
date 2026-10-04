# Step A: confirmation-gated checkout (demo ordering)

Prepares Sarah for the real Swiggy platform (see SWIGGY_INTEGRATION_RESEARCH.md). Works today in the mock, where
every order is **simulated** and labelled as such.

## Flow
    "checkout" -> address (asked only if there are several, then remembered) -> full summary
    (items, total, payment, address) -> "Do you want to proceed with placing this order to this address?"
    -> explicit "yes" -> place order -> confirmation + empty cart

## Safety rules (each one has a test)
- A "yes" counts **only directly after the summary, and only once**. Any other message cancels the pending
  confirmation, so a late or stray "yes" cannot order anything.
- If the cart changed after the summary (for example through the REST API), Sarah shows the new summary instead
  of ordering.
- A dropped connection while ordering never produces "order placed". Sarah says she cannot confirm and asks the
  user to check their orders first (ordering is not safe to retry blindly).
- Orders can be switched off per environment (`ALLOW_REAL_ORDERS`, default **false** for real Swiggy; the mock
  always allows its simulated orders).
- The mock enforces the documented order cap (₹1000) and cash-on-delivery only, like the real platform.
- Cancellation is not a platform capability: Sarah sends the user to Swiggy customer care (080-67466729).
- Mock addresses have no phone numbers (the real API returns one per address; that is PII we must not keep).

## Code
| Where | What |
|---|---|
| platform/base.py | New optional capabilities `get_addresses`, `place_order` (default: unsupported) |
| mock-mcp tools.py, data.py | Synthetic addresses, simulated `place_order`, cap and validation |
| assistant/nlu.py | Intents `place_order`, `cancel_order`; natural confirmations ("yes please") |
| assistant/state.py | `Confirmation`, remembered address, `choose_address` pending action |
| assistant/graph.py | Checkout nodes, single-use confirmation, changed-cart check |
| frontend Cards.tsx | Confirmation card (buttons are disabled once the conversation moves on) |

## Verified
Backend 184 tests, frontend 80 tests, strict typecheck, lint, production build, and the full flow over real HTTP
through the Next.js proxy.

## Behaviour changes versus the previous version
"checkout", "place my order" and "pay now" used to be refused; they now start checkout. "cancel my order" and
"refund" are redirected to customer care. Other payment questions are still declined.
