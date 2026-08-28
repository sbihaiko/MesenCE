#!/usr/bin/env python3
"""mep_recipe_common — dependency-free leaf shared by `mep_recipe.py` (the
CLI: validate/dry-run/apply) and `mep_recipe_assemble.py` (CI-side
assembly). Holds only the symbols both need, so neither imports the other
(ADR-0138 Clarification §23/§24: splits in scripts/ break cycles with a
leaf module, never with lazy in-function imports). stdlib only."""
from __future__ import annotations

import re

RECIPE_VERSION = 1
SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")


class RecipeError(Exception):
    """User-facing validation or apply failure."""
