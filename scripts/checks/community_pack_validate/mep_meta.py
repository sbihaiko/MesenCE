"""Upsert-mep-meta step structural checks for community-pack-validate.yml (T6).

Covers the "Upsert mep-meta comment" step (ADR-0138 §5/§13/§16/§18): it
runs on every successful classify+apply-verdict pass regardless of
recipe_status (never gated on recipe_status == 'present'), finds an
existing marked comment via `gh api` and PATCHes it (POSTs only when none
exists yet), the marker appears both in the find-query and the built body,
the exact literal provenance line about submitter-declared/verified-on-install
dep digests is present, the body/payload is built with Python's json
module (never bash string concatenation), and the deps/recipe_hash fields
are omitted entirely (never emitted empty/null) when no recipe was
assembled.
"""
from ._shared import fail

MEP_META_MARKER = "<!-- mep-meta -->"
MEP_META_PROVENANCE_LINE = "dep digests: submitter-declared, verified on install"
MEP_META_WRONG_GATE = "steps.assemble-recipe.outputs.recipe_status == 'present'"


def _mep_meta_block(text):
    blocks = [b for b in text.split("\n      - name:") if "id: upsert-mep-meta" in b]
    if not blocks:
        fail("Upsert mep-meta comment step (id: upsert-mep-meta) not found")
        return None
    return blocks[0]


def check_mep_meta_step_present_and_not_gated_on_recipe_status(text):
    # T6 (ADR-0138 §5/§13): the upsert runs on EVERY successful
    # classify+apply-verdict pass, regardless of recipe_status — it must
    # never be gated on recipe_status == 'present' (that would drop
    # provenance for every 'absent'/'refused' submission, which still has
    # a real verdict/labels/hash to record).
    block = _mep_meta_block(text)
    if block is None:
        return
    if "steps.classify.outcome" not in block:
        fail("Upsert mep-meta comment step does not gate on steps.classify.outcome")
    if MEP_META_WRONG_GATE in block:
        fail(
            "Upsert mep-meta comment step is gated on recipe_status == "
            "'present' — it must run on every pass regardless of recipe_status"
        )
    if "steps.apply-verdict.outputs.verdict" not in block or "steps.apply-verdict.outputs.labels" not in block:
        fail("Upsert mep-meta comment step does not consume apply-verdict's verdict/labels outputs")


def check_mep_meta_find_then_patch(text):
    # T6 (ADR-0138 §5): find the marked comment via `gh api`, then PATCH it
    # wholesale; POST a new comment only when none exists yet.
    block = _mep_meta_block(text)
    if block is None:
        return
    if "gh api" not in block:
        fail("Upsert mep-meta comment step does not call 'gh api'")
    if MEP_META_MARKER not in block:
        fail(f"Upsert mep-meta comment step does not search for the marker: {MEP_META_MARKER}")
    if "--method PATCH" not in block:
        fail("Upsert mep-meta comment step never PATCHes an existing comment")
    if "--method POST" not in block:
        fail("Upsert mep-meta comment step never POSTs a new comment when none exists")


def check_mep_meta_marker_in_comment_body(text):
    # T6: the marker must appear in the BUILT comment body itself (not
    # just the find-query above), so a fresh comment is itself discoverable
    # on the next pass.
    block = _mep_meta_block(text)
    if block is None:
        return
    if block.count(MEP_META_MARKER) < 2:
        fail(
            "Upsert mep-meta comment step must reference the marker twice: "
            "once to find an existing comment, once inside the body it writes"
        )


def check_mep_meta_provenance_line(text):
    # T6 (ADR-0138 §16): the literal line stating dep digests are
    # submitter-declared and verified only on install, exactly as worded
    # in the ADR — never paraphrased.
    block = _mep_meta_block(text)
    if block is None:
        return
    if MEP_META_PROVENANCE_LINE not in block:
        fail(f"Upsert mep-meta comment step is missing the literal provenance line: {MEP_META_PROVENANCE_LINE}")


def check_mep_meta_body_built_via_python_json(text):
    # T6: the request body (including the embedded metadata block) is
    # built with Python's json module, never bash string concatenation.
    block = _mep_meta_block(text)
    if block is None:
        return
    if "import json" not in block:
        fail("Upsert mep-meta comment step does not build its payload with Python's json module")
    if "json.dumps(" not in block or "json.dump(" not in block:
        fail("Upsert mep-meta comment step does not call json.dumps/json.dump to build the comment body/payload")


def check_mep_meta_fence_not_hardcoded(text):
    # T4 (ADR-0138 §33): json.dumps does not escape backticks, so a
    # hardcoded exactly-3-backtick fence truncates early when the payload
    # itself (a submitter-supplied hints/license value inside the embedded
    # recipe) contains a run of 3+ backticks. The writer must compute its
    # fence length via the shared "shortest safe fence" rule
    # (mep_recipe_common.choose_fence) instead of a literal ```json/```
    # pair.
    block = _mep_meta_block(text)
    if block is None:
        return
    if '"```json"' in block:
        fail("Upsert mep-meta comment step still hardcodes a fixed-length ```json opening fence")
    if '"```",' in block:
        fail("Upsert mep-meta comment step still hardcodes a fixed-length ``` closing fence")
    if "mep_recipe_common" not in block:
        fail("Upsert mep-meta comment step does not import mep_recipe_common for the shared fence rule")
    if "choose_fence(" not in block:
        fail("Upsert mep-meta comment step never calls choose_fence() to size its JSON fence")


def check_mep_meta_omits_deps_and_recipe_hash_when_absent(text):
    # T6 (ADR-0138 §13/§18): deps/recipe_hash fields are omitted entirely
    # (never emitted empty/null) when no recipe was assembled.
    block = _mep_meta_block(text)
    if block is None:
        return
    if 'recipe_status == "present"' not in block:
        fail(
            "Upsert mep-meta comment step does not condition the deps/"
            "recipe_hash fields on recipe_status == 'present'"
        )
    if '"recipe_hash"' not in block or '"deps"' not in block:
        fail("Upsert mep-meta comment step never emits deps/recipe_hash fields at all")
