"""Conversational state. Plain pydantic models so they serialize to JSON (memory or Redis)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .budget import Plan

MAX_HISTORY = 20


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class Ref(BaseModel):
    """A thing the assistant showed the user, so later turns can say 'the second one'."""
    id: str
    name: str
    restaurant_id: str | None = None
    price_inr: int | None = None


class Pending(BaseModel):
    """The assistant asked a clarifying question and is waiting for the user's choice."""
    action: Literal["add_to_cart", "show_menu", "choose_address"]
    quantity: int = 1
    candidates: list[Ref]


class Confirmation(BaseModel):
    """What the user was shown and asked to confirm. A 'yes' only counts while this is set, and only once."""
    address_id: str
    address_line: str
    total_inr: float
    payment_method: str = "COD"


class MealRequest(BaseModel):
    """A meal-planning request being filled in across turns (dish, people, budget)."""
    query: str | None = None
    people: int | None = None
    budget: int | None = None
    veg: bool | None = None
    wants_drinks: bool = False
    drink_query: str | None = None


class ConversationState(BaseModel):
    session_id: str
    history: list[Turn] = Field(default_factory=list)
    last_restaurants: list[Ref] = Field(default_factory=list)
    last_items: list[Ref] = Field(default_factory=list)
    selected_restaurant_id: str | None = None
    last_cart_item_id: str | None = None
    pending: Pending | None = None
    last_shown: Literal["restaurants", "items"] | None = None
    meal_request: MealRequest | None = None
    last_plans: list[Plan] = Field(default_factory=list)
    plan_budget: int | None = None
    address_id: str | None = None       # delivery address chosen for this conversation
    address_line: str | None = None
    confirmation: Confirmation | None = None

    def add_turn(self, role: str, text: str) -> None:
        self.history.append(Turn(role=role, text=text))
        self.history = self.history[-MAX_HISTORY:]
