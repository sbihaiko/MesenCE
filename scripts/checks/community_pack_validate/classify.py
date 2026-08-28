"""Classify-step structural checks for community-pack-validate.yml (F6.0, F6.2b).

Covers the classify step's timeout-minutes cap (F6.0) and its --json-schema
shape (ADR-0138 §4): the nested, optional recipe fragment's own `required`
array, the top-level `required` array staying unchanged by that addition,
and the absence of any `sources` (hash-bearing) schema property — classify
never computes hashes, only a deterministic later step does.
"""
import re

from ._shared import fail

CLASSIFY_TOP_LEVEL_REQUIRED = '"required":["verdict","assets","comment"]'
CLASSIFY_RECIPE_FRAGMENT_REQUIRED = '"required":["ops","deps","pack"]'
CLASSIFY_SOURCES_HASH_PROPERTY = '"sources":{"type"'


def _classify_block(text):
    blocks = [b for b in text.split("\n      - name:") if "Classify pack" in b]
    if not blocks:
        fail("Classify pack step not found")
        return None
    return blocks[0]


def check_classify_timeout(text):
    # F6.0: the LLM classify step must carry timeout-minutes so a hung
    # Claude Code Action cannot hold the runner for the job's 6-hour
    # default. The autofix step is a different Claude Code Action and is
    # not required to have the same cap.
    blocks = [b for b in text.split("\n      - name:") if "Classify pack" in b]
    if not blocks:
        fail("Classify pack step not found")
        return
    classify = blocks[0]
    if "timeout-minutes:" not in classify:
        fail("Classify pack step has no timeout-minutes (F6.0)")
        return
    match = re.search(r"timeout-minutes:\s*(\d+)", classify)
    if not match:
        fail("Classify pack step timeout-minutes is not a positive integer")
        return
    minutes = int(match.group(1))
    if minutes < 1:
        fail(f"Classify pack step timeout-minutes must be >= 1, got {minutes}")


def check_classify_recipe_fragment_required(text):
    # F6.2b (ADR-0138 §4): classify's --json-schema gains an OPTIONAL
    # nested `recipe` property (the non-derivable ops/deps/pack fragment)
    # whose OWN `required` array is exactly ["ops","deps","pack"] — this
    # is separate from, and does not replace, the top-level required list.
    classify = _classify_block(text)
    if classify is None:
        return
    if CLASSIFY_RECIPE_FRAGMENT_REQUIRED not in classify:
        fail(
            "Classify pack --json-schema missing nested recipe-fragment "
            f"required literal: {CLASSIFY_RECIPE_FRAGMENT_REQUIRED}"
        )


def check_classify_top_level_required_unchanged(text):
    # Adding the optional `recipe` property must never make it, or
    # anything else, required at the top level (ADR-0138 §2: the gate is
    # inert when classify emits no recipe at all).
    classify = _classify_block(text)
    if classify is None:
        return
    if CLASSIFY_TOP_LEVEL_REQUIRED not in classify:
        fail(
            "Classify pack --json-schema top-level required literal changed "
            f"or missing: {CLASSIFY_TOP_LEVEL_REQUIRED}"
        )


def check_classify_schema_no_sources_field(text):
    # ADR-0138 §4: classify (the LLM) never computes hashes, so `sources`
    # (the hash-bearing block) MUST NOT appear anywhere in this file's
    # schemas — it is only ever built by a deterministic step.
    if CLASSIFY_SOURCES_HASH_PROPERTY in text:
        fail(
            "a 'sources' schema property was found — classify must never "
            "emit/validate a sources/hash field (ADR-0138 §4)"
        )
