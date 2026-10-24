"""The evaluation suite runs in CI: it must pass its release gates, and its checks must catch real failures."""
from evals.runner import CLAIMS_ORDER, gate, grounding_problems, load_cases, run_all, scores


async def test_eval_suite_meets_release_gates():
    results = await run_all()
    s = scores(results)
    failures = [f"{c.id}: {t.say!r} {t.failures}" for c in results for t in c.turns if t.failures]
    assert not gate(s), "\n".join(failures)
    assert len(results) >= 30


def test_cases_file_is_valid():
    cases = load_cases()
    allowed = {"say", "intent", "calls", "not_calls", "no_tools", "reply_has", "reply_not"}
    for c in cases:
        assert c["turns"], c["id"]
        for t in c["turns"]:
            assert "say" in t and set(t) <= allowed, (c["id"], t)


TOOL_DATA = [{"lines": [{"name": "Masala Dosa", "line_total_inr": 180}], "total_inr": 210},
             [{"id": "r-002", "name": "Sample Dosa Corner (Synthetic)"}], {"order_id": "ORD-SIM-0001"}]


def test_grounding_accepts_amounts_names_and_ids_from_tools():
    reply = "Order ORD-SIM-0001 from Sample Dosa Corner (Synthetic): Masala Dosa ₹180, total ₹210."
    assert grounding_problems(reply, TOOL_DATA, "add 2 masala dosa") == []


def test_grounding_flags_invented_facts():
    assert grounding_problems("Total ₹199.", TOOL_DATA, "hi")
    assert grounding_problems("From Imaginary Cafe (Synthetic).", TOOL_DATA, "hi")
    assert grounding_problems("Order ORD-SIM-0042 is confirmed.", TOOL_DATA, "hi")


def test_grounding_allows_user_amounts_and_counts():
    assert grounding_problems("Nothing fits ₹500.", TOOL_DATA, "dosa for two under 500") == []
    assert grounding_problems("The cheapest is ₹420 for two.", TOOL_DATA, "dosa for two") == []  # 210 x 2


def test_order_claims_are_detected():
    assert CLAIMS_ORDER.search("Done! Order ORD-SIM-0001 is confirmed.")
    assert not CLAIMS_ORDER.search("Okay, I won't place the order.")
