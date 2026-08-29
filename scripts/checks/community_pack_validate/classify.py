"""Classify-step structural checks for community-pack-validate.yml (F6.0, F6.2b, F6.5).

Since F6.5 (ADR-0138, single source) the classify prompt and its JSON schema
live in `.github/ai/validate-classify.md` — the CI "Classify pack" step renders
that file via the prepare-classify-prompt step and never carries an inline
schema anymore. These checks therefore validate the SCHEMA block of the .md
(loaded through _shared) for the F6.0/F6.2b contract, and additionally assert
the workflow actually wires the classify step to the prepare step's outputs.

Contract covered:
- classify step keeps a timeout-minutes cap (F6.0);
- the schema's nested, optional recipe fragment's own `required` array is
  exactly ["ops","deps","pack"] and the top-level `required` array stays
  ["verdict","assets","comment"] (ADR-0138 §4 / §2) — validated against the
  .md SCHEMA block, which is the only copy that exists;
- no `sources` (hash-bearing) schema property anywhere (classify never
  computes hashes) — checked on the .md text as well as the workflow;
- the classify step references steps.prepare-classify-prompt outputs
  classify_prompt/classify_schema, and that prepare step renders the .md
  (both placeholders).
"""
import re

from ._shared import fail, prompt_block, prompt_text, schema_block

CLASSIFY_TOP_LEVEL_REQUIRED = '"required":["verdict","assets","comment"]'
CLASSIFY_RECIPE_FRAGMENT_REQUIRED = '"required":["ops","deps","pack"]'
CLASSIFY_SOURCES_HASH_PROPERTY = '"sources":{"type"'
PROMPT_MARKER = "<!-- PROMPT -->"
SCHEMA_MARKER = "<!-- SCHEMA -->"


def _classify_block(text):
    blocks = [b for b in text.split("\n      - name:") if "Classify pack" in b]
    if not blocks:
        fail("Classify pack step not found")
        return None
    return blocks[0]


def _prepare_block(text):
    # Match on the step's `id:` (unique) rather than the display name or a
    # bare "prepare-classify-prompt" mention: comments elsewhere in the
    # workflow legitimately reference the pattern by name (e.g. the autofix
    # prepare step's "mirroring the prepare-classify-prompt step" note), so
    # a name/substring match can grab the wrong step.
    blocks = [
        b for b in text.split("\n      - name:")
        if "id: prepare-classify-prompt" in b
    ]
    if not blocks:
        fail("prepare-classify-prompt step not found")
        return None
    return blocks[0]


def check_classify_timeout(text):
    # F6.0: the LLM classify step must carry timeout-minutes so a hung
    # Claude Code Action cannot hold the runner for the job's 6-hour
    # default. The autofix step is a different Claude Code Action and is
    # not required to have the same cap.
    classify = _classify_block(text)
    if classify is None:
        return
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
    # F6.2b (ADR-0138 §4): the schema's nested, OPTIONAL `recipe` property
    # (the non-derivable ops/deps/pack fragment) has its OWN `required`
    # array exactly ["ops","deps","pack"]. Since F6.5 the schema is only
    # rendered from .github/ai/validate-classify.md, so validate the .md.
    schema = schema_block()
    if not schema:
        fail(
            "Could not read .github/ai/validate-classify.md — cannot validate "
            "the classify schema's recipe-fragment required array"
        )
        return
    if CLASSIFY_RECIPE_FRAGMENT_REQUIRED not in schema:
        fail(
            "Classify schema (from .github/ai/validate-classify.md) missing "
            f"nested recipe-fragment required literal: "
            f"{CLASSIFY_RECIPE_FRAGMENT_REQUIRED}"
        )


def check_classify_top_level_required_unchanged(text):
    # ADR-0138 §2: adding the optional `recipe` property must never make it,
    # or anything else, required at the top level (the gate is inert when
    # classify emits no recipe at all). Validated against the .md SCHEMA.
    schema = schema_block()
    if not schema:
        fail(
            "Could not read .github/ai/validate-classify.md — cannot validate "
            "the classify schema's top-level required array"
        )
        return
    if CLASSIFY_TOP_LEVEL_REQUIRED not in schema:
        fail(
            "Classify schema (from .github/ai/validate-classify.md) top-level "
            f"required literal changed or missing: {CLASSIFY_TOP_LEVEL_REQUIRED}"
        )


def check_classify_schema_no_sources_field(text):
    # ADR-0138 §4: classify (the LLM) never computes hashes, so `sources`
    # (the hash-bearing block) MUST NOT appear anywhere — not in the
    # workflow's inline copies (if any ever return) and not in the single
    # source .md that the classify step renders.
    if CLASSIFY_SOURCES_HASH_PROPERTY in text:
        fail(
            "a 'sources' schema property was found in the workflow — classify "
            "must never emit/validate a sources/hash field (ADR-0138 §4)"
        )
    if CLASSIFY_SOURCES_HASH_PROPERTY in prompt_text():
        fail(
            "a 'sources' schema property was found in "
            ".github/ai/validate-classify.md — classify must never "
            "emit/validate a sources/hash field (ADR-0138 §4)"
        )


def check_classify_step_references_prepare_outputs(text):
    # F6.5 (ADR-0138, single source): the classify step must consume the
    # prompt/schema rendered from the .md by prepare-classify-prompt — not
    # inline literals, which is exactly the drift this wiring removes.
    classify = _classify_block(text)
    if classify is None:
        return
    if (
        "${{ steps.prepare-classify-prompt.outputs.classify_prompt }}" not in classify
        or "${{ steps.prepare-classify-prompt.outputs.classify_schema }}" not in classify
    ):
        fail(
            "Classify pack step must reference steps.prepare-classify-prompt "
            "outputs classify_prompt and classify_schema (F6.5 single source, "
            "ADR-0138)"
        )


def check_prepare_classify_prompt_renders_md(text):
    # F6.5: prepare-classify-prompt must read .github/ai/validate-classify.md
    # and render both placeholders, mirroring validate_pack_local.sh.
    prepare = _prepare_block(text)
    if prepare is None:
        return
    if ".github/ai/validate-classify.md" not in prepare:
        fail(
            "prepare-classify-prompt step must read "
            ".github/ai/validate-classify.md (F6.5 single source, ADR-0138)"
        )
    if "{{ISSUE_NUMBER}}" not in prepare or "{{EXTERNAL_ASSETS_SUFFIX}}" not in prepare:
        fail(
            "prepare-classify-prompt step must render both "
            "{{ISSUE_NUMBER}} and {{EXTERNAL_ASSETS_SUFFIX}} placeholders"
        )


def check_prompt_file_markers(text):
    # The single source must actually expose PROMPT and SCHEMA blocks that
    # the extraction (rsplit on the LAST marker) can find, and the two
    # placeholders the prompt needs must exist in the PROMPT block.
    raw = prompt_text()
    if not raw:
        fail("Could not read .github/ai/validate-classify.md")
        return
    if PROMPT_MARKER not in raw or SCHEMA_MARKER not in raw:
        fail(
            ".github/ai/validate-classify.md must contain both "
            f"{PROMPT_MARKER} and {SCHEMA_MARKER} markers"
        )
        return
    prompt = prompt_block()
    if not prompt:
        fail(".github/ai/validate-classify.md PROMPT block is empty")
        return
    if "{{ISSUE_NUMBER}}" not in prompt or "{{EXTERNAL_ASSETS_SUFFIX}}" not in prompt:
        fail(
            ".github/ai/validate-classify.md PROMPT block must contain "
            "{{ISSUE_NUMBER}} and {{EXTERNAL_ASSETS_SUFFIX}} placeholders"
        )
    if SCHEMA_MARKER in prompt:
        fail(".github/ai/validate-classify.md PROMPT block leaks the SCHEMA marker")
