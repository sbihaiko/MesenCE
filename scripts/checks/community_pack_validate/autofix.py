"""Autofix-step structural checks for community-pack-validate.yml (ADR-0138, single source).

The autofix subsystem (mep_lint.py drift autofix) is dormant by default
(`LIVE_VALIDATION_ENABLED: 'false'`), but when it runs it is a second LLM
step, so it must obey the same single-source contract as classify (F6.5):
the prompt and JSON schema live in `.github/ai/validate-autofix.md`, the
workflow's `prepare-autofix-prompt` step renders that file, and the
"Autofix mep_lint.py drift" step consumes the rendered outputs — never an
inline copy.

Contract covered:
- the autofix step references steps.prepare-autofix-prompt outputs
  autofix_prompt/autofix_schema (no inline prompt/schema);
- the prepare step reads .github/ai/validate-autofix.md and renders both
  placeholders ({{DRIFT_LINES}}, {{GAME}});
- the .md exposes PROMPT and SCHEMA blocks and keeps the schema literal
  out of the PROMPT block;
- the PROMPT block keeps the data-not-instruction clause (the autofix step
  reads untrusted third-party pack output).
"""
from ._shared import (
    autofix_prompt_block,
    autofix_prompt_text,
    autofix_schema_block,
    fail,
)

AUTOFIX_FILE = ".github/ai/validate-autofix.md"
AUTOFIX_SCHEMA_LITERAL = '"converged":{"type":"boolean"}'
PROMPT_MARKER = "<!-- PROMPT -->"
SCHEMA_MARKER = "<!-- SCHEMA -->"


def _autofix_block(text):
    blocks = [b for b in text.split("\n      - name:") if "Autofix mep_lint.py drift" in b]
    if not blocks:
        fail("Autofix mep_lint.py drift step not found")
        return None
    return blocks[0]


def _prepare_block(text):
    blocks = [
        b for b in text.split("\n      - name:")
        if "prepare-autofix-prompt" in b or "Prepare autofix prompt" in b
    ]
    if not blocks:
        fail("prepare-autofix-prompt step not found")
        return None
    return blocks[0]


def check_autofix_step_references_prepare_outputs(text):
    # Single source (ADR-0138): the autofix step must consume the
    # prompt/schema rendered from the .md by prepare-autofix-prompt — not
    # inline literals, exactly like classify.
    block = _autofix_block(text)
    if block is None:
        return
    if (
        "${{ steps.prepare-autofix-prompt.outputs.autofix_prompt }}" not in block
        or "${{ steps.prepare-autofix-prompt.outputs.autofix_schema }}" not in block
    ):
        fail(
            "Autofix step must reference steps.prepare-autofix-prompt outputs "
            "autofix_prompt and autofix_schema (single source, ADR-0138)"
        )
    if AUTOFIX_SCHEMA_LITERAL in block:
        fail(
            "Autofix step carries an inline schema copy — the schema must live "
            "only in " + AUTOFIX_FILE + " (single source, ADR-0138)"
        )


def check_prepare_autofix_prompt_renders_md(text):
    # The prepare step must read the .md and render both placeholders,
    # mirroring prepare-classify-prompt.
    prepare = _prepare_block(text)
    if prepare is None:
        return
    if AUTOFIX_FILE not in prepare:
        fail(
            "prepare-autofix-prompt step must read "
            + AUTOFIX_FILE + " (single source, ADR-0138)"
        )
    if "{{DRIFT_LINES}}" not in prepare or "{{GAME}}" not in prepare:
        fail(
            "prepare-autofix-prompt step must render both {{DRIFT_LINES}} "
            "and {{GAME}} placeholders"
        )


def check_autofix_prompt_file_markers(text):
    # The single source must expose PROMPT/SCHEMA blocks and keep the
    # schema literal out of the PROMPT block.
    raw = autofix_prompt_text()
    if not raw:
        fail("Could not read " + AUTOFIX_FILE)
        return
    if PROMPT_MARKER not in raw or SCHEMA_MARKER not in raw:
        fail(
            AUTOFIX_FILE + " must contain both "
            f"{PROMPT_MARKER} and {SCHEMA_MARKER} markers"
        )
        return
    prompt = autofix_prompt_block()
    if not prompt:
        fail(AUTOFIX_FILE + " PROMPT block is empty")
        return
    if "{{DRIFT_LINES}}" not in prompt or "{{GAME}}" not in prompt:
        fail(
            AUTOFIX_FILE + " PROMPT block must contain {{DRIFT_LINES}} "
            "and {{GAME}} placeholders"
        )
    if SCHEMA_MARKER in prompt:
        fail(AUTOFIX_FILE + " PROMPT block leaks the SCHEMA marker")
    schema = autofix_schema_block()
    if not schema or AUTOFIX_SCHEMA_LITERAL not in schema:
        fail(
            AUTOFIX_FILE + " SCHEMA block missing the converged/summary "
            "contract (" + AUTOFIX_SCHEMA_LITERAL + ")"
        )


def check_autofix_prompt_data_not_instruction(text):
    # The autofix prompt reasons about output from untrusted third-party
    # pack content; the data-not-instruction clause must live in the .md
    # PROMPT block too.
    prompt = autofix_prompt_block()
    if not prompt:
        fail("Cannot validate autofix data-not-instruction clause: PROMPT block missing")
        return
    lowered = prompt.lower()
    if "data" not in lowered or "never" not in lowered:
        fail(
            AUTOFIX_FILE + " PROMPT block lacks an explicit "
            "data-not-instruction clause"
        )
