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

# The single-source classify prompt/schema file (ADR-0138, F6.5): both the CI
# "Classify pack" step (via prepare-classify-prompt) and the local harness
# (scripts/validate_pack_local.sh) render this file, so the schema-contract
# checks read it directly instead of an inline workflow copy.
PROMPT_FILE = REPO_ROOT / ".github" / "ai" / "validate-classify.md"

_prompt_cache = None


def prompt_text():
    """The .github/ai/validate-classify.md contents (cached), or '' if missing."""
    global _prompt_cache
    if _prompt_cache is None:
        try:
            _prompt_cache = PROMPT_FILE.read_text(encoding="utf-8")
        except OSError:
            _prompt_cache = ""
    return _prompt_cache


def prompt_block():
    """The <!-- PROMPT --> body (mirrors validate_pack_local.sh's rsplit)."""
    text = prompt_text()
    if not text:
        return ""
    return text.rsplit("<!-- PROMPT -->", 1)[1].rsplit("<!-- SCHEMA -->", 1)[0].strip()


def schema_block():
    """The <!-- SCHEMA --> body (mirrors validate_pack_local.sh's rsplit)."""
    text = prompt_text()
    if not text:
        return ""
    return text.rsplit("<!-- SCHEMA -->", 1)[1].strip()


FAILURES = []


def fail(msg):
    FAILURES.append(msg)
