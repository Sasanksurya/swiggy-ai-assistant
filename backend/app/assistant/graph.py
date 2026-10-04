"""LangGraph workflow: understand -> route(intent) -> one node per capability -> finalize.

Every fact in a reply (names, prices, delivery fees, statuses) is copied from a tool result.
Nothing is generated or assumed. Capabilities the platform lacks produce an honest message.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ..platform.base import PlatformResult
from .budget import MAX_PEOPLE, Plan, build_plans, cheapest_possible
from .nlu import NLU, NLUResult
from .resolve import match_by_name, pick_by_index
from .state import Confirmation, ConversationState, MealRequest, Pending, Ref
from .tools import ToolRunner

MAX_QTY = 20
MAX_LIST = 8


class GraphState(TypedDict, total=False):
    message: str
    conv: ConversationState
    runner: ToolRunner
    nlu: NLUResult
    intent: str
    target: Ref | None
    quantity_override: int | None
    reply: str
    cards: dict[str, Any]


def inr(n) -> str:
    return f"₹{n:g}" if isinstance(n, (int, float)) else f"₹{n}"


def _item_ref(i: dict) -> Ref:
    return Ref(id=i["id"], name=i["name"], restaurant_id=i.get("restaurant_id"), price_inr=i.get("price_inr"))


def _cart_text(cart: dict) -> str:
    if not cart.get("lines"):
        return "Your cart is empty."
    lines = [f"• {l['quantity']} × {l['name']} — {inr(l['line_total_inr'])}" for l in cart["lines"]]
    return "\n".join(lines + [f"Subtotal {inr(cart['subtotal_inr'])} + delivery {inr(cart['delivery_fee_inr'])}"
                              f" = {inr(cart['total_inr'])}"])


def _fail(res: PlatformResult, what: str) -> str:
    code = res.error.code if res.error else "error"
    if code == "unsupported_capability":
        return f"Sorry, I can't {what} right now: {res.error.message}"
    if code == "mcp_unavailable":
        return f"I couldn't reach the food service to {what}. Please try again in a moment."
    if code == "restaurant_conflict":
        return ("Your cart already has items from another restaurant. Remove those first "
                "(say 'remove <item>'), then add this one.")
    if code == "item_unavailable":
        return "Sorry, that item isn't available right now."
    if code == "not_found":
        return f"I couldn't find that ({what})."
    return f"Sorry, I couldn't {what}: {res.error.message if res.error else 'unknown error'}"


def build_assistant_graph(nlu_engine: NLU, assistant_name: str = "Sarah", allow_orders: bool = True):
    # ---------- helpers that call tools ----------
    async def cart_refs(run: ToolRunner) -> tuple[PlatformResult, list[Ref]]:
        res = await run.call("get_cart")
        refs = [Ref(id=l["item_id"], name=l["name"], price_inr=l["unit_price_inr"])
                for l in (res.data or {}).get("lines", [])] if res.ok else []
        return res, refs

    async def restaurant_names(run: ToolRunner) -> dict[str, str]:
        res = await run.call("search_restaurants")
        return {r["id"]: r["name"] for r in res.data} if res.ok else {}

    # ---------- nodes ----------
    async def understand(s: GraphState) -> dict:
        conv = s["conv"]
        res = await nlu_engine.parse(s["message"], has_pending=conv.pending is not None)
        mr = conv.meal_request
        if mr and not conv.pending:  # Sarah asked for a missing detail: "500" / "two people" / "biryani"
            bare = res.intent == "select" and res.ref_index is not None and not res.query
            if bare:
                num = res.ref_index
                if mr.people is None and (num <= MAX_PEOPLE or mr.budget is not None):
                    res.people = num
                elif mr.budget is None:
                    res.max_price = num
                res.ref_index = None
            if res.intent in {"select", "unknown", "plan_meal", "search_menu"} and (
                    res.people is not None or res.max_price is not None or res.query or bare):
                res.intent = "plan_meal"
            elif res.intent != "plan_meal":
                conv.meal_request = None  # the user moved on
        out: dict[str, Any] = {"nlu": res, "intent": res.intent, "target": None, "quantity_override": None}
        pend = conv.pending
        if pend:
            cands = pend.candidates
            target = None
            if res.intent == "select" or res.ref_index:
                target = pick_by_index(cands, res.ref_index)
            if not target and res.intent == "affirm" and len(cands) == 1:
                target = cands[0]
            if not target and res.query:
                m = match_by_name(cands, res.query)
                target = m[0] if len(m) == 1 else None
            if res.intent == "deny":
                conv.pending = None
            elif target:
                conv.pending = None
                out.update(intent=pend.action, target=target, quantity_override=pend.quantity)
            elif res.intent == "select":
                out["intent"] = "invalid_choice"
            elif res.intent not in {"affirm"}:
                conv.pending = None  # the user moved on
        if conv.confirmation and out["intent"] not in {"affirm", "deny"}:
            conv.confirmation = None  # the user moved on, so an earlier summary can no longer be confirmed
        out["conv"] = conv
        return out

    async def greet(s):
        return {"reply": f"Hi, I'm {assistant_name}, your food assistant. Tell me what you're craving, how many "
                         "people are eating and your budget, and I'll find the best option and add it to your "
                         "cart. For example: 'biryani for two under 500'."}

    async def help_(s):
        caps = s["runner"]._p.capabilities()
        can = [t for t, ok in [("search restaurants and menus", caps.get("search_menu")),
                               ("add, change or remove cart items", caps.get("add_to_cart")),
                               ("check order status and details", caps.get("get_order_status"))] if ok]
        body = ", ".join(can) if can else "nothing yet, the food service isn't connected"
        can_order = bool(caps.get("place_order")) and allow_orders
        tail = ("I can place your order once you confirm it (cash on delivery), but I can't cancel orders; "
                "Swiggy customer care handles that." if can_order else "I can't place or cancel orders.")
        return {"reply": f"I'm {assistant_name}. I can {body}, and plan a meal for your group within a budget. "
                         f"{tail}"}

    async def search_restaurants(s):
        conv, n, run = s["conv"], s["nlu"], s["runner"]
        res = await run.call("search_restaurants", query=n.query or "", max_price_for_two_inr=n.max_price)
        if not res.ok:
            return {"reply": _fail(res, "search restaurants")}
        rows = res.data[:MAX_LIST]
        if not rows:
            return {"reply": "I couldn't find any matching restaurants.", "cards": {"restaurants": []}}
        conv.last_restaurants = [Ref(id=r["id"], name=r["name"]) for r in rows]
        conv.last_shown = "restaurants"
        lines = [f"{i}. {r['name']} — {', '.join(r['cuisines'])}, about {inr(r['price_for_two_inr'])} for two, "
                 f"{r['delivery_time_min']} min{'' if r['is_open'] else ' (closed)'}" for i, r in enumerate(rows, 1)]
        return {"reply": "Here's what I found:\n" + "\n".join(lines) +
                         "\nSay 'show the menu of the first one' to see dishes.",
                "cards": {"restaurants": rows}, "conv": conv}

    async def show_menu(s):
        conv, n, run = s["conv"], s["nlu"], s["runner"]
        target: Ref | None = s.get("target")
        if not target and n.ref_index and conv.last_restaurants:
            target = pick_by_index(conv.last_restaurants, n.ref_index)
        if not target and n.query:
            m = match_by_name(conv.last_restaurants, n.query)
            if len(m) == 1:
                target = m[0]
            elif not m:
                found = await run.call("search_restaurants", query=n.query)
                if not found.ok:
                    return {"reply": _fail(found, "look up that restaurant")}
                cands = [Ref(id=r["id"], name=r["name"]) for r in found.data]
                if len(cands) == 1:
                    target = cands[0]
                elif cands:
                    conv.pending = Pending(action="show_menu", candidates=cands[:5])
                    opts = "\n".join(f"{i}. {c.name}" for i, c in enumerate(cands[:5], 1))
                    return {"reply": f"Which restaurant?\n{opts}", "conv": conv}
                else:
                    return {"reply": f"I couldn't find a restaurant matching '{n.query}'."}
            else:
                conv.pending = Pending(action="show_menu", candidates=m[:5])
                opts = "\n".join(f"{i}. {c.name}" for i, c in enumerate(m[:5], 1))
                return {"reply": f"Which restaurant?\n{opts}", "conv": conv}
        if not target and conv.selected_restaurant_id and not n.ref_index:
            target = Ref(id=conv.selected_restaurant_id, name="this restaurant")
        if not target:
            return {"reply": "Which restaurant's menu would you like? Search for restaurants first, "
                             "then say 'show the menu of the first one'."}
        res = await run.call("get_menu", restaurant_id=target.id)
        if not res.ok:
            return {"reply": _fail(res, "load the menu")}
        rest, items = res.data["restaurant"], res.data["items"]
        shown = [i for i in items if i["available"]]
        if n.veg is True:
            shown = [i for i in shown if i["veg"]]
        elif n.veg is False:
            shown = [i for i in shown if not i["veg"]]
        if n.max_price is not None:
            shown = [i for i in shown if i["price_inr"] <= n.max_price]
        conv.selected_restaurant_id = rest["id"]
        conv.last_items = [_item_ref(i) for i in shown]
        conv.last_shown = "items"
        hidden = len(items) - len([i for i in items if i["available"]])
        if not shown:
            return {"reply": f"No matching available items at {rest['name']}.", "conv": conv,
                    "cards": {"restaurant": rest, "items": []}}
        lines = [f"{i}. {x['name']} — {inr(x['price_inr'])}{'' if x['veg'] else ' (non-veg)'}"
                 for i, x in enumerate(shown, 1)]
        note = f"\n({hidden} unavailable item{'s' if hidden != 1 else ''} not shown)" if hidden else ""
        return {"reply": f"Menu at {rest['name']}:\n" + "\n".join(lines) + note +
                         "\nSay 'add 2 <dish>' or 'add the second one'.",
                "conv": conv, "cards": {"restaurant": rest, "items": shown}}

    async def search_menu(s):
        conv, n, run = s["conv"], s["nlu"], s["runner"]
        res = await run.call("search_menu", query=n.query or "", max_price_inr=n.max_price,
                             veg_only=n.veg is True)
        if not res.ok:
            return {"reply": _fail(res, "search the menu")}
        items = [i for i in res.data if n.veg is not False or not i["veg"]]
        if n.max_price is not None:
            items.sort(key=lambda i: i["price_inr"])
        items = items[:MAX_LIST]
        if not items:
            return {"reply": "I couldn't find any matching dishes. Try a different dish or a higher budget.",
                    "cards": {"items": []}}
        names = await restaurant_names(run)
        conv.last_items = [_item_ref(i) for i in items]
        conv.last_shown = "items"
        lines = [f"{i}. {x['name']} — {inr(x['price_inr'])} at {names.get(x['restaurant_id'], x['restaurant_id'])}"
                 for i, x in enumerate(items, 1)]
        return {"reply": "Here's what I found:\n" + "\n".join(lines) +
                         "\nSay 'add the first one' or 'add 2 <dish>'.",
                "conv": conv, "cards": {"items": items}}

    async def add_to_cart(s):
        conv, n, run = s["conv"], s["nlu"], s["runner"]
        qty = s.get("quantity_override") or n.quantity or 1
        if qty > MAX_QTY or qty < 1:
            return {"reply": f"I can add between 1 and {MAX_QTY} of an item at a time."}
        target: Ref | None = s.get("target")
        if not target and n.ref_index:
            if conv.last_shown == "restaurants":
                return {"reply": "That's a restaurant. Say 'show the menu of the first one' to see its dishes."}
            target = pick_by_index(conv.last_items, n.ref_index)
            if not target:
                return {"reply": "I don't have an item with that number. Search for dishes first."}
        if not target and n.query:
            m = match_by_name(conv.last_items, n.query)
            if len(m) != 1:
                found = await run.call("search_menu", query=n.query, max_price_inr=n.max_price,
                                       veg_only=n.veg is True)
                if not found.ok:
                    return {"reply": _fail(found, "search for that dish")}
                m = [_item_ref(i) for i in found.data]
            if len(m) == 1:
                target = m[0]
            elif not m:
                return {"reply": f"I couldn't find '{n.query}'. Try searching for dishes first."}
            else:
                cands = m[:5]
                conv.pending = Pending(action="add_to_cart", quantity=qty, candidates=cands)
                opts = "\n".join(f"{i}. {c.name} — {inr(c.price_inr)}" for i, c in enumerate(cands, 1))
                return {"reply": f"Which one would you like?\n{opts}", "conv": conv}
        if not target:
            return {"reply": "What would you like to add? For example 'add 2 masala dosa'."}
        res = await run.call("add_to_cart", item_id=target.id, quantity=qty)
        if not res.ok:
            return {"reply": _fail(res, "add that to your cart")}
        conv.last_cart_item_id = target.id
        return {"reply": f"Added {qty} × {target.name}.\n{_cart_text(res.data)}", "conv": conv,
                "cards": {"cart": res.data}}

    async def _cart_target(s) -> tuple[Ref | None, str | None]:
        conv, n, run = s["conv"], s["nlu"], s["runner"]
        res, refs = await cart_refs(run)
        if not res.ok:
            return None, _fail(res, "read your cart")
        if not refs:
            return None, "Your cart is empty."
        if n.ref_index:
            t = pick_by_index(refs, n.ref_index)
        elif n.query:
            m = match_by_name(refs, n.query)
            t = m[0] if len(m) == 1 else None
            if len(m) > 1:
                return None, "That matches more than one cart item. Which one? " + ", ".join(r.name for r in m)
        else:
            t = next((r for r in refs if r.id == conv.last_cart_item_id), None)
        if not t:
            return None, "I couldn't tell which cart item you mean. Say 'show cart' to see them."
        return t, None

    async def update_cart(s):
        conv, n, run = s["conv"], s["nlu"], s["runner"]
        if n.quantity is None:
            return {"reply": "What quantity would you like? For example 'make it 3'."}
        if n.quantity > MAX_QTY:
            return {"reply": f"I can set quantities between 1 and {MAX_QTY}."}
        t, err = await _cart_target(s)
        if err:
            return {"reply": err}
        if n.quantity == 0:
            res = await run.call("remove_from_cart", item_id=t.id)
            verb = f"Removed {t.name}."
        else:
            res = await run.call("update_cart", item_id=t.id, quantity=n.quantity)
            verb = f"Updated {t.name} to {n.quantity}."
        if not res.ok:
            return {"reply": _fail(res, "update your cart")}
        conv.last_cart_item_id = t.id
        return {"reply": f"{verb}\n{_cart_text(res.data)}", "conv": conv, "cards": {"cart": res.data}}

    async def remove_from_cart(s):
        conv, run = s["conv"], s["runner"]
        t, err = await _cart_target(s)
        if err:
            return {"reply": err}
        res = await run.call("remove_from_cart", item_id=t.id)
        if not res.ok:
            return {"reply": _fail(res, "remove that")}
        return {"reply": f"Removed {t.name}.\n{_cart_text(res.data)}", "cards": {"cart": res.data}}

    async def view_cart(s):
        res = await s["runner"].call("get_cart")
        if not res.ok:
            return {"reply": _fail(res, "read your cart")}
        return {"reply": _cart_text(res.data), "cards": {"cart": res.data}}

    async def order_status(s):
        n, run = s["nlu"], s["runner"]
        if not n.order_id:
            return {"reply": "Which order? Please give me the order ID, for example 'status of ORD-DEMO-1002'."}
        res = await run.call("get_order_status", order_id=n.order_id)
        if not res.ok:
            return {"reply": _fail(res, "check that order")}
        st = res.data["status"].replace("_", " ").lower()
        return {"reply": f"Order {n.order_id} is {st}.", "cards": {"order": res.data}}

    async def order_details(s):
        n, run = s["nlu"], s["runner"]
        if not n.order_id:
            return {"reply": "Which order? Please give me the order ID."}
        res = await run.call("get_order_details", order_id=n.order_id)
        if not res.ok:
            return {"reply": _fail(res, "load that order")}
        o, lines = res.data, []
        for it in o["items"]:
            d = await run.call("get_item_details", item_id=it["item_id"])
            lines.append(f"• {it['quantity']} × {d.data['name'] if d.ok else it['item_id']}")
        st = o["status"].replace("_", " ").lower()
        return {"reply": f"Order {o['order_id']} ({st}):\n" + "\n".join(lines) + f"\nTotal {inr(o['total_inr'])}",
                "cards": {"order": o}}

    def _plan_text(plan: Plan) -> str:
        meta = ", ".join(x for x in [f"{plan.rating:g}★" if plan.rating is not None else "",
                                      f"{plan.delivery_time_min} min" if plan.delivery_time_min else ""] if x)
        lines = [f"• {l.quantity} × {l.name} — {inr(l.price_inr * l.quantity)}" for l in plan.lines]
        return f"{plan.restaurant_name}{f' ({meta})' if meta else ''}\n" + "\n".join(lines)

    def _plan_header(plan: Plan) -> str:
        meta = ", ".join(x for x in [f"{plan.rating:g}★" if plan.rating is not None else "",
                                      f"{plan.delivery_time_min} min" if plan.delivery_time_min else ""] if x)
        return f"{plan.restaurant_name}{f' ({meta})' if meta else ''}"

    async def _apply_plan(run: ToolRunner, plan: Plan) -> PlatformResult:
        res = None
        for l in plan.lines:
            res = await run.call("add_to_cart", item_id=l.item_id, quantity=l.quantity)
            if not res.ok:
                return res
        return res

    async def _clear_lines(run: ToolRunner, lines: list[dict]) -> PlatformResult | None:
        for l in lines:
            res = await run.call("remove_from_cart", item_id=l["item_id"])
            if not res.ok:
                return res
        return None

    def _alternatives(plans: list[Plan]) -> str:
        if len(plans) < 2:
            return ""
        rows = [f"{i}. {p.restaurant_name} — {inr(p.subtotal_inr)} (items, before delivery)"
                for i, p in enumerate(plans[1:], 2)]
        return "\nOther options:\n" + "\n".join(rows) + "\nSay 'use option 2' to switch."

    async def plan_meal(s):
        conv, n, run = s["conv"], s["nlu"], s["runner"]
        mr = conv.meal_request or MealRequest()
        if n.query:
            mr.query = n.query
        if n.people is not None:
            mr.people = n.people
        if n.max_price is not None:
            mr.budget = n.max_price
        if n.veg is not None:
            mr.veg = n.veg
        if n.wants_drinks:
            mr.wants_drinks, mr.drink_query = True, n.drink_query or mr.drink_query
        conv.meal_request = mr
        if mr.people is not None and not 1 <= mr.people <= MAX_PEOPLE:
            mr.people = None
            return {"reply": f"I can plan for 1 to {MAX_PEOPLE} people. How many are eating?", "conv": conv}
        if not mr.query:
            return {"reply": "What would you like to eat? For example 'biryani'.", "conv": conv}
        if mr.people is None:
            return {"reply": f"Sure, {mr.query}! How many people are eating?", "conv": conv}
        if mr.budget is None:
            return {"reply": f"Got it, {mr.query} for {mr.people}. What's your budget in rupees?", "conv": conv}

        conv.meal_request = None
        people, budget = mr.people, mr.budget
        rres = await run.call("search_restaurants")
        if not rres.ok:
            return {"reply": _fail(rres, "look up restaurants")}
        restaurants = {r["id"]: r for r in rres.data}
        mres = await run.call("search_menu", query=mr.query, veg_only=mr.veg is True)
        if not mres.ok:
            return {"reply": _fail(mres, "search the menu")}
        mains = [i for i in mres.data if mr.veg is not False or not i["veg"]]
        drinks: list[dict] = []
        if mr.wants_drinks:
            dres = await run.call("search_menu", query=mr.drink_query or "beverage")
            drinks = dres.data if dres.ok else []
        plans = build_plans(mains, drinks, restaurants, people, budget, mr.wants_drinks)
        if not plans:
            low = cheapest_possible(mains, drinks, restaurants, people, mr.wants_drinks)
            if low is None:
                return {"reply": f"I couldn't find any open restaurant serving {mr.query}."}
            return {"reply": f"I couldn't fit {mr.query} for {people} within {inr(budget)}. The cheapest I found "
                             f"is {inr(low)} for {people}. Want to try a higher budget?"}
        conv.last_plans, conv.plan_budget = plans, budget
        top = plans[0]

        cart = await run.call("get_cart")
        if cart.ok and cart.data["lines"]:
            return {"reply": f"Best match for {people} within {inr(budget)}:\n{_plan_text(top)}\n"
                             "Your cart already has items, so I haven't changed it. Remove them (say 'remove "
                             "<item>') and say 'use option 1', or say 'use option 1' now to replace your cart."
                             + _alternatives(plans), "conv": conv, "cards": {"plans": [p.model_dump() for p in plans], "budget_inr": budget,
                                    "people": people}}
        res = await _apply_plan(run, top)
        if not res.ok:
            return {"reply": _fail(res, "add that to your cart")}
        note = ""
        if res.data["total_inr"] > budget:  # delivery fee (from the platform) pushed the total over: re-plan once
            fee = res.data["delivery_fee_inr"]
            alt = build_plans(mains, drinks, restaurants, people, budget - fee, mr.wants_drinks)
            if alt:
                err = await _clear_lines(run, res.data["lines"])
                if err:
                    return {"reply": _fail(err, "adjust your cart")}
                res2 = await _apply_plan(run, alt[0])
                if not res2.ok:
                    return {"reply": _fail(res2, "add that to your cart")}
                plans, top, res = alt, alt[0], res2
                conv.last_plans = plans
                note = f"The {inr(fee)} delivery fee would have gone over your budget, so I adjusted the order. "
        total = res.data["total_inr"]
        status = (f"That's {inr(budget - total)} under your budget of {inr(budget)}." if total <= budget
                  else f"Heads up: this is {inr(total - budget)} over your budget of {inr(budget)} including delivery.")
        drinks_note = "\nI couldn't fit the drinks you asked for." if mr.wants_drinks and not top.drinks_ok else ""
        conv.last_cart_item_id = top.lines[-1].item_id
        return {"reply": f"For {people} within {inr(budget)}, my pick is {_plan_header(top)}. {note}"
                         f"I've added it to your cart:\n{_cart_text(res.data)}\n{status}{drinks_note}"
                         + _alternatives(plans),
                "conv": conv, "cards": {"plan": top.model_dump(), "plans": [p.model_dump() for p in plans],
                                        "cart": res.data, "budget_inr": budget, "people": people}}

    async def use_plan(s):
        conv, n, run = s["conv"], s["nlu"], s["runner"]
        if not conv.last_plans:
            return {"reply": "I don't have any meal options yet. Tell me what you'd like, for example "
                             "'biryani for two under 500'."}
        plan = pick_by_index(conv.last_plans, n.ref_index)  # type: ignore[arg-type]
        if not plan:
            return {"reply": f"Please pick an option between 1 and {len(conv.last_plans)}."}
        cart = await run.call("get_cart")
        if not cart.ok:
            return {"reply": _fail(cart, "read your cart")}
        err = await _clear_lines(run, cart.data["lines"])
        if err:
            return {"reply": _fail(err, "update your cart")}
        res = await _apply_plan(run, plan)
        if not res.ok:
            return {"reply": _fail(res, "add that to your cart")}
        total, budget = res.data["total_inr"], conv.plan_budget
        over = f"\nHeads up: that's {inr(total - budget)} over your budget of {inr(budget)} including delivery." \
            if budget and total > budget else ""
        conv.last_cart_item_id = plan.lines[-1].item_id
        return {"reply": f"Switched your cart to {_plan_header(plan)}:\n{_cart_text(res.data)}{over}",
                "conv": conv, "cards": {"plan": plan.model_dump(), "cart": res.data,
                                **({"budget_inr": budget} if budget else {})}}

    async def select(s):
        conv, n = s["conv"], s["nlu"]
        if conv.last_shown == "restaurants":
            return await show_menu(s)
        if conv.last_shown == "items":
            t = pick_by_index(conv.last_items, n.ref_index)
            if not t:
                return {"reply": "I don't have an option with that number."}
            conv.pending = Pending(action="add_to_cart", quantity=1, candidates=[t])
            return {"reply": f"Add 1 × {t.name} ({inr(t.price_inr)}) to your cart? Say 'yes' or 'no'.",
                    "conv": conv}
        return {"reply": "Search for restaurants or dishes first, then pick one."}

    async def invalid_choice(s):
        k = len(s["conv"].pending.candidates)
        return {"reply": f"Please pick a number between 1 and {k}."}

    # ---------- checkout: address -> summary -> explicit yes -> place ----------
    async def _summary(s, cart: dict, note: str = "") -> dict:
        conv, run = s["conv"], s["runner"]
        names = await restaurant_names(run)
        restaurant = names.get(cart.get("restaurant_id"), "your restaurant")
        conv.confirmation = Confirmation(address_id=conv.address_id, address_line=conv.address_line,
                                         total_inr=cart["total_inr"])
        return {"reply": f"{note}Here's your order from {restaurant}:\n{_cart_text(cart)}\n"
                         f"Payment: cash on delivery.\nDelivering to: {conv.address_line}.\n"
                         "Do you want to proceed with placing this order to this address? "
                         "Say 'yes' to place it or 'no' to cancel.",
                "conv": conv,
                "cards": {"cart": cart, "checkout": {"restaurant": restaurant, "address": conv.address_line,
                                                     "payment_method": "COD", "total_inr": cart["total_inr"],
                                                     "requires_confirmation": True}}}

    async def _begin_checkout(s) -> dict:
        conv, run = s["conv"], s["runner"]
        if not allow_orders:
            return {"reply": "Placing orders is switched off in this environment, so I can only fill your cart."}
        cart_res = await run.call("get_cart")
        if not cart_res.ok:
            return {"reply": _fail(cart_res, "place your order")}
        cart = cart_res.data
        if not cart["lines"]:
            return {"reply": "Your cart is empty. Tell me what you'd like first, for example "
                             "'biryani for two under 500'."}
        if not conv.address_id:
            ares = await run.call("get_addresses")
            if not ares.ok:
                return {"reply": _fail(ares, "load your delivery addresses")}
            if not ares.data:
                return {"reply": "You don't have a saved delivery address. Please add one in the Swiggy app first."}
            if len(ares.data) == 1:
                conv.address_id, conv.address_line = ares.data[0]["id"], ares.data[0]["address_line"]
            else:
                cands = [Ref(id=a["id"], name=f"{a['category']}: {a['address_line']}") for a in ares.data[:5]]
                conv.pending = Pending(action="choose_address", candidates=cands)
                opts = "\n".join(f"{i}. {c.name}" for i, c in enumerate(cands, 1))
                return {"reply": f"Where should I deliver this?\n{opts}", "conv": conv}
        return await _summary(s, cart)

    async def place_order(s):
        return await _begin_checkout(s)

    async def choose_address(s):
        conv, target = s["conv"], s["target"]
        conv.address_id, conv.address_line = target.id, target.name.split(": ", 1)[-1]
        return await _begin_checkout(s)

    async def affirm(s):
        conv, run = s["conv"], s["runner"]
        conf = conv.confirmation
        if not conf:
            return {"reply": "There's nothing waiting for your confirmation. What would you like to do?"}
        conv.confirmation = None  # single use: this yes can never place a second order
        if not allow_orders:
            return {"reply": "Placing orders is switched off in this environment, so I haven't ordered anything."}
        cart_res = await run.call("get_cart")
        if not cart_res.ok:
            return {"reply": _fail(cart_res, "place your order")}
        cart = cart_res.data
        if not cart["lines"]:
            return {"reply": "Your cart is empty now, so I haven't placed anything."}
        if cart["total_inr"] != conf.total_inr:
            return await _summary(s, cart, note="Your cart changed since I showed you the summary, "
                                                "so please check it again.\n")
        res = await run.call("place_order", address_id=conf.address_id, payment_method=conf.payment_method)
        if not res.ok:
            code = res.error.code if res.error else ""
            if code == "mcp_unavailable":  # ordering is not safe to retry blindly
                return {"reply": "I couldn't confirm whether your order went through. Please check your orders "
                                 "before trying again, so you don't order twice."}
            if code in {"cart_cap_exceeded", "empty_cart"}:
                return {"reply": f"I can't place this order: {res.error.message}. Remove something and ask me again."}
            return {"reply": _fail(res, "place your order")}
        o = res.data
        after = await run.call("get_cart")  # the cart is empty after a successful order
        status = str(o.get("status", "CONFIRMED")).replace("_", " ").lower()
        demo = " This is a simulated demo order. Nothing was ordered or charged." if res.synthetic else ""
        conv.last_cart_item_id, conv.last_plans, conv.plan_budget = None, [], None
        return {"reply": f"Done! Order {o['order_id']} is {status}. Total {inr(o.get('total_inr', conf.total_inr))}, "
                         f"cash on delivery, delivering to {conf.address_line}.{demo}",
                "conv": conv, "cards": {"order": o, **({"cart": after.data} if after.ok else {})}}

    async def deny(s):
        conv = s["conv"]
        if conv.confirmation:
            conv.confirmation = None
            return {"reply": "Okay, I won't place the order. Your cart is unchanged.", "conv": conv}
        return {"reply": "Okay, no problem."}

    async def cancel_order(s):
        demo = " (This demo has no real orders.)" if s["runner"]._p.source == "mock" else ""
        return {"reply": "I can't cancel orders. To cancel a Swiggy order, please call Swiggy customer care "
                         f"at 080-67466729.{demo}"}

    async def unsupported_action(s):
        return {"reply": "I can't help with payments or refunds. I can build your cart and, once you confirm it, "
                         "place the order as cash on delivery."}

    async def unknown(s):
        return {"reply": "Sorry, I didn't get that. Try 'veg biryani under 250', 'show pizza restaurants', "
                         "'add 2 masala dosa' or 'show cart'."}

    async def finalize(s):
        conv = s["conv"]
        conv.add_turn("user", s["message"])
        conv.add_turn("assistant", s["reply"])
        return {"conv": conv}

    # ---------- wiring ----------
    nodes = {"greet": greet, "help": help_, "search_restaurants": search_restaurants, "show_menu": show_menu,
             "search_menu": search_menu, "add_to_cart": add_to_cart, "update_cart": update_cart,
             "remove_from_cart": remove_from_cart, "view_cart": view_cart, "order_status": order_status,
             "order_details": order_details, "select": select, "plan_meal": plan_meal, "use_plan": use_plan, "invalid_choice": invalid_choice,
             "affirm": affirm, "deny": deny, "unsupported_action": unsupported_action, "unknown": unknown,
             "place_order": place_order, "choose_address": choose_address, "cancel_order": cancel_order}
    g = StateGraph(GraphState)
    g.add_node("understand", understand)
    for name, fn in nodes.items():
        g.add_node(name, fn)
        g.add_edge(name, "finalize")
    g.add_node("finalize", finalize)
    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", lambda s: s["intent"] if s["intent"] in nodes else "unknown",
                            {k: k for k in nodes})
    g.add_edge("finalize", END)
    return g.compile()
