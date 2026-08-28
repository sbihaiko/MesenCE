"""Shared state for community-pack-validate.yml's topic-module checks.

Every check_*() function across the sibling topic modules in this package
(general, classify, assemble_recipe, recipe_gate, apply_verdict, mep_meta)
appends to this same FAILURES list via fail(), so the entry point
(scripts/checks/verify_community_pack_validate_workflow.py) can report every
failure gathered across every module in one pass (ADR-0138 Clarification
S23, F6.2c).
"""
from pathlib import Path

# scripts/checks/community_pack_validate/_shared.py -> parents[3] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
