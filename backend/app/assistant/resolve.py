"""Pure helpers that resolve what the user is referring to ('the second one', 'the dosa')."""
from __future__ import annotations

import re

from .state import Ref


def pick_by_index(refs: list[Ref], idx: int | None) -> Ref | None:
    if idx is None or not refs:
        return None
    if idx == -1:
        return refs[-1]
    return refs[idx - 1] if 1 <= idx <= len(refs) else None


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def match_by_name(refs: list[Ref], text: str | None) -> list[Ref]:
    """Refs whose id equals the text, or whose name contains every word of the text."""
    if not text:
        return []
    for r in refs:
        if r.id.lower() == text.strip().lower():
            return [r]
    want = _tokens(text)
    if not want:
        return []
    return [r for r in refs if all(any(w == t or t.startswith(w) or w.startswith(t) and len(t) > 2
                                       for t in _tokens(r.name)) for w in want)]
