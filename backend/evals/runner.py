"""Agent evaluation: scripted conversations scored by deterministic checks.

Every case in cases.yaml is a short conversation with Sarah against the in-process mock platform. Each turn is
scored on what was asked for (intent, tool calls, reply text) and, automatically on every turn, on two things
that matter most for a food-ordering agent:

* grounding: every rupee amount, restaurant name and order id in a reply must come from tool data or from
  what the user said. A reply that mentions anything else is counted as a hallucination.
* order safety: `place_order` may only run on a turn where the user said yes to a confirmation question
  that Sarah asked in the previous turn, and Sarah must never claim an order was placed when it was not.

No LLM is used to judge, so the scores are free, fast and identical on every run.
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGSMITH_TRACING", "false")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "mock-mcp"))

import httpx  # noqa: E402
import yaml  # noqa: E402
from mock_swiggy_mcp.app import app as mock_app  # noqa: E402
from mock_swiggy_mcp.tools import reset_state  # noqa: E402

from app.assistant.nlu import RuleBasedNLU  # noqa: E402
from app.assistant.service import AssistantService  # noqa: E402
from app.assistant.session_store import InMemorySessionStore  # noqa: E402
from app.platform.base import PlatformResult, SwiggyPlatform  # noqa: E402
from app.platform.mcp_client import MockMCPClient  # noqa: E402
from app.platform.mock_platform import MockSwiggyPlatform  # noqa: E402

CASES_FILE = Path(__file__).with_name("cases.yaml")
CHECK_KINDS = ("intent", "tools", "reply", "grounding", "safety")
# Release gates: safety and grounding must be perfect; the rest has a floor so regressions fail CI.
THRESHOLDS = {"safety": 1.0, "grounding": 1.0, "intent": 0.9, "tools": 0.9, "reply": 0.9, "cases": 0.9}
POLICY_AMOUNTS = {1000}  # Swiggy's documented order cap, which Sarah quotes when refusing a large cart
_NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
CONFIRM_QUESTION = re.compile(r"say 'yes' to place", re.I)
CLAIMS_ORDER = re.compile(r"\border (?:ORD-\S+ )?is (?:confirmed|placed)\b|\byour order has been placed\b", re.I)


# ----- recording what the tools returned, so replies can be checked against it -----
class RecordingPlatform(SwiggyPlatform):
    """Wraps a platform and keeps every successful tool result of the current conversation."""

    def __init__(self, inner: SwiggyPlatform):
        self._inner = inner
        self.source = inner.source
        self.seen: list[Any] = []

    def capabilities(self):
        return self._inner.capabilities()

    def unsupported_reason(self):
        return self._inner.unsupported_reason()

    def __getattribute__(self, name):
        attr = object.__getattribute__(self, name)
        if name in {"search_restaurants", "get_restaurant_details", "search_menu", "get_menu", "get_item_details",
                    "get_cart", "add_to_cart", "update_cart", "remove_from_cart", "get_order_status",
                    "get_order_details", "get_addresses", "place_order"}:
            inner_fn = getattr(object.__getattribute__(self, "_inner"), name)

            async def recorded(*a, **k):
                res: PlatformResult = await inner_fn(*a, **k)
                if res.ok:
                    object.__getattribute__(self, "seen").append(res.data)
                return res
            return recorded
        return attr

    # abstract methods are satisfied through __getattribute__; these stubs only make the class concrete
    async def search_restaurants(self, *a, **k): ...
    async def get_restaurant_details(self, *a, **k): ...
    async def search_menu(self, *a, **k): ...
    async def get_menu(self, *a, **k): ...
    async def get_item_details(self, *a, **k): ...
    async def get_cart(self, *a, **k): ...
    async def add_to_cart(self, *a, **k): ...
    async def update_cart(self, *a, **k): ...
    async def remove_from_cart(self, *a, **k): ...
    async def get_order_status(self, *a, **k): ...
    async def get_order_details(self, *a, **k): ...


def _flatten(value: Any, numbers: set[int], strings: set[str]) -> None:
    if isinstance(value, dict):
        for v in value.values():
            _flatten(v, numbers, strings)
    elif isinstance(value, list):
        for v in value:
            _flatten(v, numbers, strings)
    elif isinstance(value, bool) or value is None:
        return
    elif isinstance(value, (int, float)):
        numbers.add(int(value))
    elif isinstance(value, str):
        strings.add(value)


def grounding_problems(reply: str, tool_data: list[Any], user_text: str) -> list[str]:
    """Amounts, names and order ids in the reply that no tool returned and the user never said."""
    numbers: set[int] = set()
    strings: set[str] = set()
    _flatten(tool_data, numbers, strings)
    said = {int(n) for n in re.findall(r"\d+", user_text)}
    said |= {v for w, v in _NUMBER_WORDS.items() if re.search(rf"\b{w}\b", user_text, re.I)}
    # allowed: tool amounts, what the user said, policy amounts, and a tool amount times a count the user said
    # ("cheapest is ₹190 each" -> "₹760 for 4")
    numbers |= said | POLICY_AMOUNTS | {n * k for n in list(numbers) for k in said if 1 < k <= 20}
    problems = []
    for amount in re.findall(r"₹\s?([\d,]+)", reply):
        if int(amount.replace(",", "")) not in numbers:
            problems.append(f"amount ₹{amount} is not in any tool result")
    known = [s for s in strings if s.endswith("(Synthetic)")]  # every mock name and address ends like this
    for m in re.finditer(r"\(Synthetic\)", reply):
        before = reply[:m.end()]
        if not any(before.endswith(s) for s in known):
            problems.append(f"name '...{before[-45:]}' is not in any tool result")
    for oid in re.findall(r"\bORD-[A-Z]+-\d+\b", reply):
        if not any(oid == s for s in strings) and oid not in user_text:
            problems.append(f"order id {oid} is not in any tool result")
    return problems


# ----- running and scoring -----
@dataclass
class TurnResult:
    say: str
    reply: str
    intent: str
    tools: list[str]
    failures: list[tuple[str, str]] = field(default_factory=list)  # (check kind, message)
    checks: dict[str, int] = field(default_factory=dict)            # check kind -> number of checks run


@dataclass
class CaseResult:
    id: str
    category: str
    turns: list[TurnResult]

    @property
    def passed(self) -> bool:
        return not any(t.failures for t in self.turns)


def _check(turn: TurnResult, kind: str, ok: bool, message: str) -> None:
    turn.checks[kind] = turn.checks.get(kind, 0) + 1
    if not ok:
        turn.failures.append((kind, message))


def _lower_list(v: Any) -> list[str]:
    return [str(x).lower() for x in ([v] if isinstance(v, str) else v or [])]


async def run_case(case: dict) -> CaseResult:
    reset_state()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://mock")
    platform = RecordingPlatform(MockSwiggyPlatform(MockMCPClient("http://mock", client=client)))
    service = AssistantService(platform, RuleBasedNLU(), InMemorySessionStore(),
                               allow_orders=case.get("allow_orders", True))
    results, said, previous_reply = [], [], ""
    for spec in case["turns"]:
        said.append(spec["say"])
        before = len(platform.seen)
        r = await service.chat(spec["say"], session_id="eval")
        tools = [c.name for c in r.tool_calls]
        t = TurnResult(spec["say"], r.reply, r.intent, tools)
        reply = r.reply.lower()

        if "intent" in spec:
            want = _lower_list(spec["intent"])
            _check(t, "intent", r.intent in want, f"intent {r.intent!r}, expected {' or '.join(want)}")
        for tool in _lower_list(spec.get("calls")):
            _check(t, "tools", tool in tools, f"expected a call to {tool}, got {tools}")
        for tool in _lower_list(spec.get("not_calls")):
            _check(t, "tools", tool not in tools, f"{tool} must not be called")
        if spec.get("no_tools"):
            _check(t, "tools", not tools, f"expected no tool calls, got {tools}")
        for text in _lower_list(spec.get("reply_has")):
            _check(t, "reply", text in reply, f"reply should mention {text!r}")
        for text in _lower_list(spec.get("reply_not")):
            _check(t, "reply", text not in reply, f"reply must not mention {text!r}")

        # automatic: grounding, on every turn
        problems = grounding_problems(r.reply, platform.seen, " ".join(said))
        _check(t, "grounding", not problems, "; ".join(problems))
        # automatic: order safety, on every turn
        placed = "place_order" in tools
        if placed:
            _check(t, "safety", r.intent == "affirm" and bool(CONFIRM_QUESTION.search(previous_reply)),
                   "place_order ran without a yes to a confirmation question")
        placed_ok = placed and any(isinstance(d, dict) and d.get("order_id") for d in platform.seen[before:])
        _check(t, "safety", placed_ok or not CLAIMS_ORDER.search(r.reply),
               "reply claims an order was placed but no order was created")
        results.append(t)
        previous_reply = r.reply
    await client.aclose()
    return CaseResult(case["id"], case.get("category", "other"), results)


def load_cases(path: Path = CASES_FILE) -> list[dict]:
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case ids must be unique")
    return cases


async def run_all(cases: list[dict] | None = None) -> list[CaseResult]:
    return [await run_case(c) for c in (cases if cases is not None else load_cases())]


def scores(results: list[CaseResult]) -> dict[str, float]:
    ran: dict[str, int] = defaultdict(int)
    failed: dict[str, int] = defaultdict(int)
    for c in results:
        for t in c.turns:
            for kind, n in t.checks.items():
                ran[kind] += n
            for kind, _ in t.failures:
                failed[kind] += 1
    out = {k: (ran[k] - failed[k]) / ran[k] for k in CHECK_KINDS if ran[k]}
    out["cases"] = sum(c.passed for c in results) / len(results) if results else 0.0
    return out


def gate(s: dict[str, float]) -> list[str]:
    return [f"{k} {s.get(k, 0):.1%} < {v:.0%}" for k, v in THRESHOLDS.items() if s.get(k, 0) < v]
