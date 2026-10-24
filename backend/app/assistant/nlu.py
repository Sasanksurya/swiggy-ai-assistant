"""Natural-language understanding: message -> intent + entities.

`NLU` is an interface so the rule-based parser (free, deterministic, offline) and an LLM-backed
parser can be swapped via config without touching the graph.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

Intent = Literal[
    "greet", "help", "search_restaurants", "search_menu", "show_menu", "add_to_cart", "update_cart",
    "remove_from_cart", "view_cart", "order_status", "order_details", "select", "affirm", "deny",
    "plan_meal", "use_plan", "place_order", "cancel_order", "unsupported_action", "unknown",
]
INTENTS: tuple[str, ...] = Intent.__args__  # type: ignore[attr-defined]


class NLUResult(BaseModel):
    intent: Intent = "unknown"
    query: str | None = None          # free text: dish / cuisine / restaurant name
    quantity: int | None = None
    max_price: int | None = None
    veg: bool | None = None           # True = veg only, False = non-veg only, None = no preference
    ref_index: int | None = None      # 1-based ordinal the user referred to; -1 = "last"
    order_id: str | None = None
    people: int | None = None         # "for two", "3 people"
    wants_drinks: bool = False
    drink_query: str | None = None    # e.g. "cola" when a specific drink is named
    confidence: float = 1.0


class NLU(ABC):
    @abstractmethod
    async def parse(self, message: str, *, has_pending: bool = False) -> NLUResult: ...


_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
              "eight": 8, "nine": 9, "ten": 10}
_ORD_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1}

_BUDGET = re.compile(
    r"\b(?:under|below|less than|within|upto|up to|max(?:imum)?|budget(?: of| is)?)\s*(?:rs\.?|inr|₹)?\s*(\d+)"
    r"|(?:₹|rs\.?|inr)\s*(\d+)\s*(?:or less|max|and below)|<\s*(\d+)"
    r"|\b(?:around|about|approx(?:imately)?|roughly|(?:in the )?range of)\s*(?:rs\.?|inr|₹)?\s*(\d{3,})"
    r"|\b(\d{2,})\s*(?:rs\.?|rupees|inr|₹)?\s*budget", re.I)
_PEOPLE = re.compile(
    r"\b(?:for\s+)?(\d{1,2}|one|two|three|four|five|six|seven|eight)\s*(?:people|persons?|ppl|guests|pax|of us|members)\b"
    r"|\bfor\s+(\d{1,2})\b(?!\s*(?:rs|rupees|inr|₹|\d))"      # digits: not a price ("for 20 rupees")
    r"|\bfor\s+(two|three|four|five|six|seven|eight)\b", re.I)
_DRINK = re.compile(r"\b(drinks?|cola|cokes?|pepsi|thums up|beverages?|soft drinks?|juice|lassi)\b", re.I)
_COLA = re.compile(r"\b(cola|cokes?|pepsi|thums up)\b", re.I)
_ORDER_ID = re.compile(r"\bORD-[A-Z0-9-]+\b", re.I)
_ORD_NUM = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b|(?:#|\bno\.?\s*|\bnumber\s+|\boption\s+)(\d+)\b", re.I)

_STOP = set("""a an the me my i we you please pls can could would will shall to of for from in on at and or with
some any it that this those these one ones is are was be do does did get give show find search suggest recommend
list tell about what whats which where there here also just like want need looking look add put include order
buy have take make update change set remove delete drop cart basket items item dishes dish options option
restaurant restaurants place places outlet outlets menu menus cheap best good nice something anything food eat
under below within upto up max maximum budget rs inr rupees less than and more only veg vegetarian non nonveg
non-veg first second third fourth fifth last quantity qty x pcs pc piece pieces plates plate
people person persons ppl guests pax members combo combos meal meals around about approx approximately roughly
range i'm im i'll ill i've hey hello hi hii ok okay namaste drink drinks cola coke cokes pepsi thums beverage
beverages soft juice lassi use switch go choose pick plan
sarah sara sarahs sera hey ok
ne mein mujhe chahiye karo kar dena dijiye hai ka ki ke ko liye wala wali bhai yaar""".split())
# The second-to-last line is the assistant's own name: voice input often starts with "Sarah, ...".
# The last line is common Hindi/Hinglish filler from speech-to-text ("biryani mein", "mujhe ... chahiye").

_ONE_PRONOUN_PREV = {"the", "that", "this", "which", "first", "second", "third", "fourth", "fifth", "last"}

_STRICT_ADD = re.compile(r"\b(add|put|include|order|buy)\b", re.I)
_SOFT_ADD = re.compile(r"\b(i want|get me|give me|i need|i'?ll have|i'?ll take|i would like|i'd like)\b", re.I)
_SEARCH_WORDS = re.compile(r"\b(find|show|search|suggest|recommend|looking|what|any|options|dish(es)?|items|"
                           r"something|anything|cheap|list|which)\b", re.I)
_CANCEL = re.compile(r"\b(cancel (my |the |this )?order|refund)\b", re.I)
_PLACE = re.compile(r"\b(checkout|check out|pay now|pay for (my |the )?order|place (my |the |an? )?order|"
                    r"confirm (my |the )?order|buy now)\b", re.I)
_UNSUPPORTED = re.compile(  # things Sarah does not do: payment talk, and dine-out (she only handles delivery)
    r"\b(payment|pay)\b|\b(book|reserve)\b.*\btables?\b|\btables?\b.*\b(booking|reservation)\b"
    r"|\breservations?\b|\bdine[- ]?(in|out)\b", re.I)


def _strip_tokens(text: str) -> str:
    toks = re.findall(r"[a-zA-Z][a-zA-Z'-]*", text)
    return " ".join(t.lower() for t in toks if t.lower() not in _STOP and len(t) > 1).strip()


class RuleBasedNLU(NLU):
    def __init__(self, assistant_name: str = "Sarah"):
        self._wake = re.compile(
            r"(?:\b(?:hey|hi|hello|ok|okay|hii)[\s,]+)?\b" + re.escape(assistant_name) + r"\b[\s,.!?:-]*", re.I)

    async def parse(self, message: str, *, has_pending: bool = False) -> NLUResult:
        raw = message.strip()
        woke = bool(self._wake.search(raw))
        raw = self._wake.sub(" ", raw).strip()   # "Hey Sarah, ..." -> "..."
        t = raw.lower()
        r = NLUResult()
        if woke and not raw:
            r.intent = "greet"
            return r

        m = _ORDER_ID.search(raw)
        if m:
            r.order_id = m.group(0).upper()
            raw_wo = _ORDER_ID.sub(" ", raw)
        else:
            raw_wo = raw

        b = _BUDGET.search(raw_wo)
        if b:
            r.max_price = int(next(g for g in b.groups() if g))
            raw_wo = _BUDGET.sub(" ", raw_wo)

        pm = _PEOPLE.search(raw_wo)
        if pm:
            val = next(g for g in pm.groups() if g).lower()
            r.people = _NUM_WORDS.get(val) or int(val)
            raw_wo = _PEOPLE.sub(" ", raw_wo)

        if _DRINK.search(t):
            r.wants_drinks = True
            r.drink_query = "cola" if _COLA.search(t) else None

        if re.search(r"\bnon[- ]?veg\b", t):
            r.veg = False
        elif re.search(r"\b(veg|vegetarian|pure veg)\b", t):
            r.veg = True

        o = _ORD_NUM.search(raw_wo)
        if o:
            r.ref_index = int(next(g for g in o.groups() if g))
            raw_wo = _ORD_NUM.sub(" ", raw_wo)
        else:
            for w, v in _ORD_WORDS.items():
                if re.search(rf"\b{w}\b", t):
                    r.ref_index = v
                    break

        qm = re.search(r"\b(\d+)\b", raw_wo)
        if qm:
            r.quantity = int(qm.group(1))
        else:
            for w, v in _NUM_WORDS.items():
                for mm in re.finditer(rf"\b{w}\b", t):
                    before = t[:mm.start()].split()
                    prev = before[-1] if before else ""
                    if w == "one" and (prev in _ONE_PRONOUN_PREV or r.ref_index is not None):
                        continue  # "the one", "that one", "2nd one" -> pronoun, not a quantity
                    r.quantity = v
                    break
                if r.quantity:
                    break

        bare = re.fullmatch(r"\s*(?:#|number\s+|option\s+)?(\d+)\s*[.!]?\s*", t)
        if bare and not b:
            r.intent, r.ref_index, r.quantity = "select", int(bare.group(1)), None
            return r

        r.query = _strip_tokens(raw_wo) or None
        if r.query:  # drop number-word and ordinal residue
            r.query = " ".join(w for w in r.query.split() if w not in _NUM_WORDS) or None

        r.intent = self._intent(t, r, has_pending)
        if r.intent in {"view_cart", "greet", "help", "affirm", "deny", "order_status", "order_details",
                        "unsupported_action", "use_plan", "place_order", "cancel_order"}:
            r.query = None
        if r.intent == "unknown":
            r.confidence = 0.2
        return r

    def _intent(self, t: str, r: NLUResult, has_pending: bool) -> str:
        if re.fullmatch(r"\s*(yes|yeah|yep|yup|sure|ok(ay)?|confirm|do it|go ahead|please do)(,?\s*(please|place it|order it|go ahead))?\s*[.!]?\s*", t):
            return "affirm"
        if re.fullmatch(r"\s*(no|nope|nah|cancel|never ?mind|stop)\s*[.!]?\s*", t):
            return "deny"
        if _CANCEL.search(t):
            return "cancel_order"
        if _PLACE.search(t):
            return "place_order"
        if _UNSUPPORTED.search(t):
            return "unsupported_action"
        if re.search(r"\b(help|what can you do|how (do|does) (you|this) work)\b", t):
            return "help"
        if r.order_id or re.search(r"\b(track|status|where is)\b.*\border\b|\border\b.*\b(status|track|where)\b", t):
            return "order_details" if re.search(r"\b(details?|items?)\b", t) else "order_status"
        if r.ref_index and re.search(r"\b(use|switch to|go with|choose|pick|take|select)\b.*\b(option|plan)\b", t):
            return "use_plan"
        if re.search(r"\bcart\b|\bbasket\b", t) and not re.search(r"\b(add|put|remove|delete|update|change)\b", t):
            return "view_cart"
        if re.search(r"\b(remove|delete|drop|take out)\b", t):
            return "remove_from_cart"
        if re.search(r"\b(change|update|modify|make (it|that)|set)\b", t) and (r.quantity is not None or r.ref_index):
            return "update_cart"
        plan_words = re.search(r"\b(combos?|meals?|plan)\b", t)
        if re.search(r"\b(restaurants?|outlets?|eateries)\b", t) and not plan_words and not _STRICT_ADD.search(t):
            return "search_restaurants"  # "restaurants under 300 for two" is a search, not a meal plan
        if (r.people is not None and (r.max_price is not None or r.query or r.wants_drinks)) or \
                (r.max_price is not None and plan_words):
            return "plan_meal"
        if _STRICT_ADD.search(t):
            return "add_to_cart"
        if _SOFT_ADD.search(t) and (r.quantity or r.ref_index) and not _SEARCH_WORDS.search(t):
            return "add_to_cart"
        if re.search(r"\bmenu\b", t):
            return "show_menu"
        if re.search(r"\b(restaurants?|places?|outlets?|eateries|near me)\b", t):
            return "search_restaurants"
        if _SEARCH_WORDS.search(t) or _SOFT_ADD.search(t) or r.max_price or r.veg is not None:
            return "search_menu"
        if re.match(r"\s*(hi|hello|hey|hii|namaste|good (morning|afternoon|evening))\b", t):
            return "greet"
        if r.ref_index and not r.query:
            return "select"
        if r.query and len(r.query.split()) <= 4:
            return "search_menu"
        return "unknown"
