"""Assemble-recipe step structural checks for community-pack-validate.yml (F6.2b).

Covers the deterministic "Assemble MEP recipe" step (ADR-0138 §13/§17):
that it exists and is gated on the classify step's outcome, calls
`mep_recipe.py assemble-sources`, fetches the issue body via `gh issue view`
(never the triggering event's payload), writes its output to the
runner-local $RUNNER_TEMP handoff path, and exposes exactly the three
literal recipe_status values.
"""
from ._shared import fail

RUNNER_TEMP_RECIPE_PATH = "$RUNNER_TEMP/mep_recipe.json"
RECIPE_STATUS_VALUES = ("absent", "present", "refused")
ISSUE_VIEW_CALL = 'gh issue view "$ISSUE_NUMBER" --repo "$REPO" --json body -q'


def _assemble_recipe_block(text):
    blocks = [b for b in text.split("\n      - name:") if "Assemble MEP recipe" in b]
    if not blocks:
        fail("Assemble MEP recipe step not found")
        return None
    return blocks[0]


def check_assemble_recipe_step_present(text):
    # F6.2b (ADR-0138 §13): a new deterministic step assembles the
    # recipe's `sources` block after classify — never the LLM, which
    # never computes hashes (§4).
    block = _assemble_recipe_block(text)
    if block is None:
        return
    if "id: assemble-recipe" not in block:
        fail("Assemble MEP recipe step missing 'id: assemble-recipe'")
    if "steps.classify.outcome" not in block:
        fail("Assemble MEP recipe step does not gate on steps.classify.outcome (must run after classify)")
    if "mep_recipe.py assemble-sources" not in block:
        fail("Assemble MEP recipe step does not call 'mep_recipe.py assemble-sources'")


def check_assemble_recipe_issue_body_via_gh(text):
    # ADR-0138 §17: the issue body is fetched via `gh issue view`, never
    # taken from the triggering event's payload (this is a reusable
    # workflow_call workflow whose caller may not even be an issues event).
    block = _assemble_recipe_block(text)
    if block is None:
        return
    if ISSUE_VIEW_CALL not in block:
        fail(f"Assemble MEP recipe step does not fetch the issue body via: {ISSUE_VIEW_CALL}")


def check_assemble_recipe_runner_temp_handoff(text):
    # ADR-0138 §13: the assembled recipe is written to a runner-local temp
    # path, never a path inside the checkout.
    block = _assemble_recipe_block(text)
    if block is None:
        return
    if RUNNER_TEMP_RECIPE_PATH not in block:
        fail(f"Assemble MEP recipe step does not reference the handoff path {RUNNER_TEMP_RECIPE_PATH}")
    if f'--out "{RUNNER_TEMP_RECIPE_PATH}"' not in block:
        fail("Assemble MEP recipe step does not pass --out pointing at the runner-local handoff path")


def check_recipe_status_three_values(text):
    # ADR-0138 §13: the step exposes exactly one output, recipe_status,
    # with exactly three literal values — absent/present/refused.
    block = _assemble_recipe_block(text)
    if block is None:
        return
    for value in RECIPE_STATUS_VALUES:
        literal = f"recipe_status={value}"
        if literal not in block:
            fail(f"Assemble MEP recipe step never emits literal '{literal}' to GITHUB_OUTPUT")
