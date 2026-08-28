"""Apply-verdict step structural checks for community-pack-validate.yml (T5).

Covers the "Apply classification verdict" step (ADR-0138 §6/§10/§13),
which stays the SOLE verdict/label writer: the recipe_ok downgrade
expression must live inside `run:` (never a step-level `if:`), the
`assets:external` label must be derived from the assembled recipe's
`sources.deps` (never classify's own enum) gated on `recipe_status ==
'present'`, and the step must expose its effective verdict/labels as step
outputs for later steps (e.g. mep-meta) to consume without re-deriving.
"""
import re

from ._shared import REPO_ROOT, fail

APPLY_VERDICT_DOWNGRADE_EXPRESSION = '[ "$RECIPE_STATUS" = "present" ] && [ "$RECIPE_OK" != "true" ]'

MEI_RULES_PATH = REPO_ROOT / "scripts" / "mei_rules.py"
# Matches the STATUS_TO_KIND = { ... } dict literal in mei_rules.py, and
# the "value" side of each of its entries (the value each Status literal
# maps to -- "mep" or "hd-legacy" today).
STATUS_TO_KIND_BLOCK_RE = re.compile(r"STATUS_TO_KIND\s*=\s*\{(.*?)\n\}", re.DOTALL)
DICT_VALUE_RE = re.compile(r':\s*"([^"]+)"')
WORKFLOW_KIND_ASSIGN_RE = re.compile(r'KIND="([^"]+)"')


def _apply_verdict_block(text):
    blocks = [b for b in text.split("\n      - name:") if "id: apply-verdict" in b]
    if not blocks:
        fail("Apply classification verdict step (id: apply-verdict) not found")
        return None
    return blocks[0]


def check_apply_verdict_downgrade_expression(text):
    # T5 (ADR-0138 §10/§13): apply-verdict stays the SOLE verdict/label
    # writer. A present-but-failing recipe may only ever downgrade an
    # `accepted` classify verdict to `invalid` — as a literal bash
    # condition inside `run:`, never a step-level `if:` (a step-level
    # `if:` would let the Actions expression engine decide whether the
    # whole verdict/label-writing step runs at all, which is not a
    # downgrade — it would skip writing anything).
    block = _apply_verdict_block(text)
    if block is None:
        return
    if APPLY_VERDICT_DOWNGRADE_EXPRESSION not in block:
        fail(
            "apply-verdict step is missing the exact downgrade expression: "
            f"{APPLY_VERDICT_DOWNGRADE_EXPRESSION}"
        )
    if re.search(r"if:\s*.*RECIPE_OK", text):
        fail(
            "a step-level `if:` referencing RECIPE_OK was found — the "
            "downgrade must live inside `run:`, never a GitHub Actions `if:`"
        )
    if 'VERDICT="invalid"' not in block:
        fail("apply-verdict step does not reassign VERDICT to \"invalid\" on downgrade")


def check_apply_verdict_external_label_branch(text):
    # T5 (ADR-0138 §6/§13): `assets:external` is derived from the
    # assembled recipe having a non-empty `sources.deps` (never from
    # classify's own `assets` enum, which has no "external" member) and
    # applied through an `external` arm added to the existing case/label
    # loop, only when recipe_status == 'present' (the only status for
    # which mep_recipe.json was actually written by the assembly step).
    block = _apply_verdict_block(text)
    if block is None:
        return
    if 'external) L="assets:external"' not in block:
        fail("apply-verdict step has no case-loop arm applying the assets:external label")
    if 'RECIPE_STATUS" = "present"' not in block:
        fail("apply-verdict step does not condition assets:external on recipe_status == 'present'")
    if "sources.deps" not in block:
        fail("apply-verdict step does not inspect the assembled recipe's sources.deps for assets:external")


def check_apply_verdict_exposes_outputs(text):
    # T5: the effective (post-downgrade) verdict and the labels actually
    # applied to the issue are exposed as apply-verdict's own step
    # outputs, so a later step (e.g. the mep-meta comment upsert) can
    # consume them without recomputing/re-deriving anything already
    # decided here.
    block = _apply_verdict_block(text)
    if block is None:
        return
    if 'echo "verdict=$VERDICT" >> "$GITHUB_OUTPUT"' not in block:
        fail("apply-verdict step does not expose its effective verdict via GITHUB_OUTPUT (verdict=...)")
    if 'echo "labels=$APPLIED_LABELS" >> "$GITHUB_OUTPUT"' not in block:
        fail("apply-verdict step does not expose the applied labels via GITHUB_OUTPUT (labels=...)")


def _mei_rules_status_to_kind_values():
    # Reads scripts/mei_rules.py's own source text directly (never
    # imported as a module -- this checker has no need for a sys.path
    # change just to read two string literals) and extracts the value
    # side of every STATUS_TO_KIND entry.
    if not MEI_RULES_PATH.is_file():
        return None
    text = MEI_RULES_PATH.read_text(encoding="utf-8")
    match = STATUS_TO_KIND_BLOCK_RE.search(text)
    if match is None:
        return None
    return set(DICT_VALUE_RE.findall(match.group(1)))


def check_apply_verdict_kind_matches_mei_rules_status_to_kind(text):
    # T4 (ADR-0138 §29): the CATEGORY_FULL_MEP/CATEGORY_PARTIAL_HD branches
    # each set a literal KIND value ("mep"/"hd-legacy") threaded into the
    # mep-meta payload's kind field via GITHUB_OUTPUT. This mirrors (never
    # re-derives) mei_rules.STATUS_TO_KIND's own pairing -- checked here by
    # reading mei_rules.py's source directly, so a drift on either side
    # fails loudly instead of silently diverging.
    block = _apply_verdict_block(text)
    if block is None:
        return
    if '"$CATEGORY_FULL_MEP") KIND="mep"' not in block:
        fail('apply-verdict step does not set KIND="mep" on the CATEGORY_FULL_MEP branch')
    if '"$CATEGORY_PARTIAL_HD") KIND="hd-legacy"' not in block:
        fail('apply-verdict step does not set KIND="hd-legacy" on the CATEGORY_PARTIAL_HD branch')
    if 'echo "kind=$KIND" >> "$GITHUB_OUTPUT"' not in block:
        fail("apply-verdict step does not expose KIND via GITHUB_OUTPUT (kind=...)")
    workflow_kinds = set(WORKFLOW_KIND_ASSIGN_RE.findall(block))
    rules_kinds = _mei_rules_status_to_kind_values()
    if rules_kinds is None:
        fail(f"could not read mei_rules.STATUS_TO_KIND from {MEI_RULES_PATH}")
        return
    if workflow_kinds != rules_kinds:
        fail(
            "apply-verdict step's KIND literals "
            f"{sorted(workflow_kinds)} are not textually consistent with "
            f"mei_rules.STATUS_TO_KIND's values {sorted(rules_kinds)}"
        )
