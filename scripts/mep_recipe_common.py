#!/usr/bin/env python3
"""mep_recipe_common — symbols shared between mep_recipe.py (validate/
dry-run/apply + CLI dispatch) and mep_recipe_assemble.py (CI-side
assemble-sources, F6.2c / ADR-0138 Clarification §23).

Both siblings import from here instead of one importing from the other,
so neither direction creates an import cycle: mep_recipe.py imports
mep_recipe_assemble (to re-expose assemble_sources/cmd_assemble_sources)
and mep_recipe_assemble.py imports mep_recipe_common (for RecipeError/
SHA256_HEX/RECIPE_VERSION) — mep_recipe_common itself imports neither
sibling, so this module is trivially importable standalone, and so is
mep_recipe_assemble (`python3 -c "import mep_recipe_assemble"` from
scripts/ no longer raises a partially-initialized-module error).

stdlib only.
"""
from __future__ import annotations

import re

RECIPE_VERSION = 1
SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")


class RecipeError(Exception):
    """User-facing validation or apply failure."""
