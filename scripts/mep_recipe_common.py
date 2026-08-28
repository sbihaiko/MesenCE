#!/usr/bin/env python3
"""mep_recipe_common — dependency-free leaf shared by `mep_recipe.py` (the
CLI: validate/dry-run/apply) and `mep_recipe_assemble.py` (CI-side
assembly). Holds only the symbols both need, so neither imports the other
(ADR-0138 Clarification §23/§24: splits in scripts/ break cycles with a
leaf module, never with lazy in-function imports). stdlib only.

Also holds the "shortest safe fence" rule (ADR-0138 §33): `json.dumps`
does not escape backticks, so a hardcoded exactly-3-backtick Markdown
fence truncates early when the JSON payload itself contains a run of 3+
backticks (e.g. a submitter-supplied `hints`/`license` string). The fix
is one rule shared by every writer and reader of a backtick-fenced
payload in this project: a writer calls `choose_fence()` to pick a fence
strictly longer than any backtick run already in the payload, and a
reader calls `find_fenced_block()`, which accepts an opening run of 3 or
more backticks and matches the closing run by that same length (never a
bare 3-backtick assumption)."""
from __future__ import annotations

import re

RECIPE_VERSION = 1
SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")

BACKTICK_RUN = re.compile(r"`+")
MIN_FENCE_BACKTICKS = 3


class RecipeError(Exception):
    """User-facing validation or apply failure."""


def max_backtick_run(payload: str) -> int:
    """Length of the longest run of consecutive backticks in `payload`, or
    0 when it contains none."""
    return max((len(run) for run in BACKTICK_RUN.findall(payload)), default=0)


def choose_fence(payload: str, min_backticks: int = MIN_FENCE_BACKTICKS) -> str:
    """Shortest backtick fence (at least `min_backticks` long) that is
    strictly longer than any backtick run already present in `payload`, so
    embedding `payload` between this fence and a matching closer never
    truncates early (ADR-0138 §33)."""
    return "`" * max(min_backticks, max_backtick_run(payload) + 1)


def find_fenced_block(text: str, label: str, min_backticks: int = MIN_FENCE_BACKTICKS) -> str | None:
    """Locate a fenced block opened by `<3+ backticks><label>` in `text` and
    return its body, matching the closing fence by the exact same
    backtick-run length as the opener — the reader side of the §33 rule.
    Returns None when no such opener, or no matching closer, is found."""
    opener = re.search(rf"(`{{{min_backticks},}}){re.escape(label)}[^\n]*\n", text)
    if opener is None:
        return None
    fence = opener.group(1)
    body_start = opener.end()
    closer = re.search(rf"(?<!`){re.escape(fence)}(?!`)", text[body_start:])
    if closer is None:
        return None
    return text[body_start : body_start + closer.start()]
