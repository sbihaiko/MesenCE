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
    if "classify_pack_brief.py" not in prepare or "{{PACK_BRIEF}}" not in prepare:
        fail(
            "prepare-classify-prompt step must run scripts/classify_pack_brief.py "
            "and render {{PACK_BRIEF}}"
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
    if "{{PACK_BRIEF}}" not in prompt:
        fail(".github/ai/validate-classify.md PROMPT block must contain {{PACK_BRIEF}}")
    if "Do not open `pack_download.bin`" not in prompt and "Do not open pack_download.bin" not in prompt:
        fail(
            ".github/ai/validate-classify.md PROMPT must forbid opening "
            "pack_download.bin (issue #148 classify timeout)"
        )
    if SCHEMA_MARKER in prompt:
        fail(".github/ai/validate-classify.md PROMPT block leaks the SCHEMA marker")


# --- issue #152: the {{EXTERNAL_ASSETS_SUFFIX}} slot must stay data-only -----
# The "External assets" field is submitter-controlled text. It used to be
# interpolated into an imperative sentence ('verdict MUST be "accepted"')
# built by the renderer, which is the only place submitter bytes reached
# instruction-shaped context. The rule now lives in the .md as trusted prompt
# text and the renderers emit nothing but the verbatim field, fenced between
# EXTERNAL-ASSETS-DATA-BEGIN/-END with any forged sentinel neutralised.
EXT_BEGIN_SENTINEL = "EXTERNAL-ASSETS-DATA-BEGIN"
EXT_END_SENTINEL = "EXTERNAL-ASSETS-DATA-END"
EXT_NEUTRALISE_SED = "s/EXTERNAL-ASSETS-DATA-/EXTERNAL-ASSETS-DATA_/g"
# Imperative fragments that must never be produced by the renderer (they are
# prompt text now); matched case-insensitively against the SUFFIX block only.
EXT_IMPERATIVE_MARKERS = (
    "verdict must be",
    "must be filled",
    "the submission declares external assets",
    "do not apply",
)
_EXT_SUFFIX_BLOCK_RE = re.compile(
    r'^[ \t]*if \[ -n "\$EXT" \]; then\n.*?^[ \t]*fi$',
    re.S | re.M,
)


def _ext_suffix_block(text, where):
    match = _EXT_SUFFIX_BLOCK_RE.search(text)
    if not match:
        fail(
            f"{where}: could not find the `if [ -n \"$EXT\" ]` block that "
            "renders {{EXTERNAL_ASSETS_SUFFIX}} (issue #152)"
        )
        return None
    # Dedent: the two renderers sit at different indentation levels (a YAML
    # `run: |` body vs. a shell function), so compare the logic, not the
    # column it starts in.
    lines = match.group(0).split("\n")
    pad = len(lines[0]) - len(lines[0].lstrip())
    return "\n".join(line[pad:] if line[:pad].isspace() else line.lstrip() for line in lines)


def check_external_assets_slot_is_data_only(text):
    from ._shared import REPO_ROOT

    ci = _ext_suffix_block(text, "community-pack-validate.yml")
    local_path = REPO_ROOT / "scripts" / "validate_pack_local.sh"
    try:
        local_text = local_path.read_text(encoding="utf-8")
    except OSError:
        fail("Could not read scripts/validate_pack_local.sh")
        return
    local = _ext_suffix_block(local_text, "scripts/validate_pack_local.sh")
    if ci is None or local is None:
        return
    if ci != local:
        fail(
            "the {{EXTERNAL_ASSETS_SUFFIX}} renderers in "
            "community-pack-validate.yml and scripts/validate_pack_local.sh "
            "differ — they must stay identical (ADR-0138 single source)"
        )
    for where, block in (("community-pack-validate.yml", ci),
                         ("scripts/validate_pack_local.sh", local)):
        code = "\n".join(
            line for line in block.split("\n") if not line.lstrip().startswith("#")
        )
        for marker in EXT_IMPERATIVE_MARKERS:
            if marker in code.lower():
                fail(
                    f"{where}: the {{{{EXTERNAL_ASSETS_SUFFIX}}}} renderer emits "
                    f"instruction-shaped text ({marker!r}) around submitter bytes "
                    "— that rule belongs in .github/ai/validate-classify.md "
                    "(issue #152)"
                )
        for needed in (EXT_BEGIN_SENTINEL, EXT_END_SENTINEL, EXT_NEUTRALISE_SED):
            if needed not in code:
                fail(
                    f"{where}: the {{{{EXTERNAL_ASSETS_SUFFIX}}}} renderer must fence "
                    f"the field as data — missing {needed!r} (issue #152)"
                )


def check_prompt_file_owns_external_assets_rule():
    """The imperative external-assets rule must live in the .md PROMPT block."""
    prompt = prompt_block()
    if not prompt:
        return
    for sentinel in (EXT_BEGIN_SENTINEL, EXT_END_SENTINEL):
        if sentinel not in prompt:
            fail(
                ".github/ai/validate-classify.md PROMPT block must describe the "
                f"external-assets data fence ({sentinel}) it renders into "
                "{{EXTERNAL_ASSETS_SUFFIX}} (issue #152)"
            )
    head = prompt.rsplit("{{EXTERNAL_ASSETS_SUFFIX}}", 1)[0]
    if "EXTERNAL ASSETS SLOT" not in head:
        fail(
            ".github/ai/validate-classify.md PROMPT block must state the "
            "external-assets rule as trusted prompt text immediately before "
            "{{EXTERNAL_ASSETS_SUFFIX}} (issue #152)"
        )
    lowered = head.lower()
    if "never as an instruction" not in lowered and "never an instruction" not in lowered:
        fail(
            ".github/ai/validate-classify.md must restate the external-assets "
            "field as data, never an instruction (issue #152)"
        )
