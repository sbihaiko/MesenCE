"""Recipe-gate step structural checks for community-pack-validate.yml (F6.2b).

Covers the "Recipe gate" step (ADR-0138 §2/§13): it must run
`mep_recipe.py validate`/`dry-run` and expose only a `recipe_ok` step
output — never write a label/comment/Status itself — and it must be gated
on the exact `== 'present'` literal, never the inverted `!= 'absent'` form
(which would also (wrongly) run for 'refused'). Also covers the file-wide
ban on `github.event.issue` (ADR-0138 §17).
"""
from ._shared import fail

RECIPE_GATE_CORRECT_CONDITION = "steps.assemble-recipe.outputs.recipe_status == 'present'"
RECIPE_GATE_WRONG_CONDITION = "steps.assemble-recipe.outputs.recipe_status != 'absent'"


def _recipe_gate_block(text):
    blocks = [b for b in text.split("\n      - name:") if "id: recipe-gate" in b]
    if not blocks:
        fail("Recipe gate step (id: recipe-gate) not found")
        return None
    return blocks[0]


def check_recipe_gate_step_present_and_gated(text):
    # ADR-0138 §2/§13: the gate must run ONLY when the assembly step
    # actually wrote a recipe ('present') and must stay inert for BOTH
    # 'absent' (no external_assets declared) and 'refused' (a dependency
    # line lacked a sha256, so 'refused' takes the pre-ADR verdict path
    # untouched). Gating on `!= 'absent'` would be wrong: it would also
    # run the gate for 'refused', which must never happen. This check
    # requires the exact `== 'present'` literal and separately (below,
    # against the whole file) forbids the inverted `!= 'absent'` form.
    block = _recipe_gate_block(text)
    if block is None:
        return
    if RECIPE_GATE_CORRECT_CONDITION not in block:
        fail(
            "Recipe gate step is not gated on the exact literal: "
            f"{RECIPE_GATE_CORRECT_CONDITION}"
        )
    if "mep_recipe.py validate" not in block:
        fail("Recipe gate step does not call 'mep_recipe.py validate'")
    if "mep_recipe.py dry-run" not in block:
        fail("Recipe gate step does not call 'mep_recipe.py dry-run'")
    if "recipe_ok=" not in block:
        fail("Recipe gate step does not emit a recipe_ok step output")
    for forbidden in ("--add-label", "gh issue comment", "STATUS_FIELD_ID"):
        if forbidden in block:
            fail(f"Recipe gate step touches a label/comment/Status write ({forbidden!r}) — it must expose only recipe_ok")


def check_recipe_gate_never_uses_inverted_condition(text):
    # ADR-0138 §2/§13 (restated): the `!= 'absent'` form must never appear
    # anywhere in this file, gate block or not — it is the specific wrong
    # form this check exists to catch.
    if RECIPE_GATE_WRONG_CONDITION in text:
        fail(
            "the inverted gating form was found (must gate on == 'present', "
            f"never != 'absent'): {RECIPE_GATE_WRONG_CONDITION}"
        )


def check_no_github_event_issue(text):
    # ADR-0138 §17: the issue body/number must come from `gh issue view`
    # plus `inputs.issue_number`, never from the triggering event's
    # payload — the verifier asserts the absence of this literal anywhere
    # in the file, not just inside the new step.
    if "github.event.issue" in text:
        fail(
            "github.event.issue was found — the issue body/number must "
            "come from gh issue view / inputs.issue_number (ADR-0138 §17)"
        )
