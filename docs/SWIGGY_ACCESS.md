# Connecting the real Swiggy platform (Builders Club)

Swiggy offers developers an official, invite-based MCP platform: <https://mcp.swiggy.com/builders/>.
This file explains what is built, what you do yourself, and how to apply. Everything below comes from
Swiggy's own documentation (links at the bottom); where the docs are silent, this file says so.

## What Swiggy's rules mean for this project
| Swiggy rule | How the app follows it |
|---|---|
| OAuth 2.1 with PKCE, no API key; the user signs in with phone + OTP on Swiggy's page | `app/platform/swiggy/oauth.py`; the app never sees the OTP |
| Clients register themselves (dynamic registration) | done once, remembered with the tokens |
| Refresh tokens rotate | one refresh at a time (lock), newest token saved, dead session means "sign in again" |
| Orders: cash on delivery, hard cap of Rs 1000 | enforced by the checkout flow and the mock |
| Show items and total, and get a clear yes before ordering | confirmation-gated checkout (see STEP_A_CHECKOUT.md) |
| `place_food_order` is not idempotent: never blind-retry | `McpHttpClient` retries only calls marked idempotent; an order is never re-sent |
| 401: refresh once; 429: wait for `Retry-After`; 5xx: backoff, 4 attempts, 30 s | implemented and tested (`tests/test_swiggy_mcp_http.py`) |
| Log a correlation id on every call | every call logs `cid=...` (never the token) |

## What works today, and what does not
Built and tested against a faithful fake of Swiggy's servers, and the MCP client was also checked against
the official MCP SDK server: sign-in, token storage and refresh, the MCP connection with its retry rules,
a read-only `doctor` command, and the sign-in routes.

**Live with real Swiggy data (read-only):** with `MOCK_MODE=false` and your account connected, Sarah can list
your saved addresses, search restaurants, and show restaurant details and menus. The mapping in
`app/platform/swiggy/mapping.py` is written from responses recorded with the doctor command and is fail-closed:
a row missing a field Sarah needs is dropped, and an unrecognised response is reported, never guessed.
Menus are paged by category, so Sarah reads the first three pages and says when a menu is partial.

**Not live yet:** cart, order status and placing orders. Their real response shapes are not recorded and they
change state, so Sarah says plainly that they are not enabled. Meal planning needs a keyword-free restaurant
list, which Swiggy's search does not offer, so "plan a meal" is also limited in real mode.

## Step 1: try the sign-in on your own computer (no approval needed, per Swiggy's quickstart)
Swiggy's quickstart says the OAuth steps run on `http://localhost` before you apply. If it turns out
Swiggy blocks this until approval, skip to Step 3.

1. `docker compose -f docker-compose.yml -f docker-compose.frontend.yml up --build -d`
2. Open <http://localhost:8000/api/swiggy/connect>. You land on Swiggy's own page; sign in with your phone
   number and the OTP. Swiggy sends you back to a page saying "Swiggy account connected".
3. Check: <http://localhost:8000/api/swiggy/status> shows `"connected": true`.

If Swiggy shows an error about the redirect URI instead, localhost is not enabled for your account yet.

## Step 2: record Swiggy's real tool schemas and responses (read-only)
```
docker compose exec backend python -m app.platform.swiggy.doctor biryani
```
It prints every Swiggy tool with its inputs (required or optional), then calls only read-only tools:
`get_addresses`, `search_restaurants`, `get_restaurant_menu`, `search_menu`, `get_food_cart`,
`fetch_food_coupons` and `get_food_orders`. Each call is built from that tool's own schema, and one refused
call does not stop the rest. Personal data (phone, email, address text, coordinates) is
replaced with `<redacted>`; read it once before sharing it. It cannot change a cart or place an order: any
other tool is refused, and a test checks that.

Paste the output into the chat and the mapping can be written from it.

## Step 3: apply for access
Apply at <https://mcp.swiggy.com/builders/access/>. Access is invite-based in v1, there is no published
review time, and Swiggy looks for a concrete use case, respect for order confirmation, correct OAuth and
401/429 handling, and a security baseline. Being approved is not guaranteed, and a personal project may be
asked follow-up questions. If the form has no video field, email builders@swiggy.in with the link.

| Form field | What to enter |
|---|---|
| Integration name | Swiggy AI Food Assistant (Sarah) |
| Organization | your name (individual developer) |
| Redirect URIs | `http://localhost:8000/api/swiggy/callback` (add an HTTPS one only if you host it) |
| Servers | `food` |
| Expected volume | under 20 orders/day and under 500 tool calls/day |
| Contact email | your email |

Use-case paragraph (edit it so every sentence is true for you):
> Sarah is a chat and voice assistant that helps a user choose and order food within a budget, for example
> "biryani for two under Rs 500". A LangGraph agent finds an open restaurant, builds a cart, and always shows
> the items, total, payment method (cash on delivery) and delivery address before asking for an explicit
> "yes". Orders above Rs 1000 are never attempted, a late or stray "yes" cannot place an order, and order
> placement is never retried blindly: after an error the app checks the order list first. Sign-in uses
> OAuth 2.1 with PKCE and rotating refresh tokens, 401 and 429 responses are handled as documented, and every
> call is logged with a correlation id. It is a personal project used by its developer and a few testers.

Demo video (2 to 3 minutes, unlisted YouTube or Drive link):
1. Show the app and the "Demo mode" banner.
2. Type "biryani for two under 500" and show the cart and budget bar.
3. Say "checkout", pick an address, show the summary and confirmation question, then say "yes".
4. Show the LangSmith trace of that turn and the green CI run on GitHub.
5. Say out loud which safety rules you follow (confirmation, cap, no blind retry).

## Safety rules for real mode
- Real mode places **real cash-on-delivery orders** on your account. `ALLOW_REAL_ORDERS` stays `false`
  until you have deliberately tested checkout, and Sarah always asks for a yes first.
- Whoever can reach the backend can talk to Sarah as your connected account. Never put a connected real-mode
  backend on the public internet. A public demo should stay in mock mode with `SWIGGY_CONNECT_ENABLED=false`
  (this switches the connect, callback and disconnect routes off).
- The token file `.swiggy_tokens.json` (or `/data/swiggy_tokens.json` in Docker) is a secret. It is ignored by
  Git and written with mode 0600. Never paste it anywhere; delete it to sign out, or `POST /api/swiggy/disconnect`.
- Staging (`https://mcp-staging.swiggy.com`, seeded data, no real orders) becomes available after Swiggy
  approves you; set `SWIGGY_BASE_URL` to use it. Production needs staging green for 48 hours.

## Sources
- [Access and onboarding](https://mcp.swiggy.com/builders/docs/operate/access/)
- [Authenticate](https://mcp.swiggy.com/builders/docs/start/authenticate/)
- [Developer quickstart](https://mcp.swiggy.com/builders/docs/start/developer/)
- [Build an agent](https://mcp.swiggy.com/builders/docs/start/developer/build-an-agent/)
- [Order food end to end](https://mcp.swiggy.com/builders/docs/build/recipes/order-food/)
- [Ship to production](https://mcp.swiggy.com/builders/docs/build/ship-to-production/)
