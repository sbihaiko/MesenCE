#!/usr/bin/env python3
"""Structural checker for community-pack-validate.yml (AC-2, AC-6 validate-side, F6.0).

Parses .github/workflows/community-pack-validate.yml with PyYAML and does
targeted substring/regex checks against the raw text for facts that don't
have a stable YAML shape (values embedded inside `if:`/`run:` strings, the
classification prompt, top-of-file comments).

The AC-6 cross-check below is a LITERAL `uses:`/string match against this
workflow's own text only — it never opens, reads, or parses
community-pack-catalog.yml (that file's own structural checker, from a
different task, covers its side of AC-6).

Usage: python3 scripts/checks/verify_community_pack_validate_workflow.py
"""
import re
import sys
from pathlib import Path

import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github" / "workflows" / "community-pack-validate.yml"
)
ALLOWLIST_PATH = Path(__file__).resolve().parents[2] / "scripts" / "pack_host_allowlist.json"
FETCH_PACK_PATH = Path(__file__).resolve().parents[2] / "scripts" / "fetch_pack.py"

REQUIRED_IDS = {
    "PVT_kwHOB1MsbM4BhjpN": "Project node id",
    "PVTSSF_lAHOB1MsbM4BhjpNzhge86c": "Status field id",
    "5173b5cd": "Status option: Novo envio",
    "51951f52": "Status option: Em validação",
    "227e4623": "Status option: Inválido",
    "39e4f3a1": "Status option: Aceito parcial HD Mesen",
    "cd763737": "Status option: Aceito MEP completo",
    "PVTF_lAHOB1MsbM4BhjpNzhge9Is": "Pack Hash field id",
}

HOST_ALLOWLIST = (
    "github.com",
    "raw.githubusercontent.com",
    "gist.githubusercontent.com",
    "gist.github.com",
)

ACEITO_MARKERS = ("STATUS_ACEITO_PARCIAL", "STATUS_ACEITO_COMPLETO", "aceito")

FAILURES = []


def fail(msg):
    FAILURES.append(msg)


def load():
    if not WORKFLOW_PATH.is_file():
        fail(f"missing file: {WORKFLOW_PATH}")
        return "", {}
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        fail(f"YAML did not parse: {exc}")
        data = {}
    return text, data


def check_workflow_call_inputs(data):
    # PyYAML resolves the bare `on:` key to the boolean True (YAML 1.1).
    on_block = data.get("on", data.get(True, {})) or {}
    wc = on_block.get("workflow_call")
    if not wc:
        fail("workflow_call trigger not declared under on:")
        return
    inputs = wc.get("inputs", {})
    for name in ("issue_number", "pack_url", "mode"):
        if name not in inputs:
            fail(f"workflow_call.inputs missing '{name}'")


def check_ids(text):
    for id_value, label in REQUIRED_IDS.items():
        if id_value not in text:
            fail(f"missing required id ({label}): {id_value}")


def check_project_number_only(text):
    if "PROJECT_NUMBER: 3" not in text:
        fail("PROJECT_NUMBER is not pinned to 3")
    for m in re.finditer(r"gh project item-(?:add|list)\s+(\d+)\b", text):
        fail(f"gh project call hardcodes a non-variable project number: {m.group(0)}")
    for m in re.finditer(r'gh project item-(?:add|list)\s+"\$([A-Z_]+)"', text):
        if m.group(1) != "PROJECT_NUMBER":
            fail(f"gh project call uses an unexpected project-number variable: {m.group(0)}")


def check_host_allowlist(text):
    # The allow-list itself lives in scripts/pack_host_allowlist.json (a
    # config file, not inline workflow YAML) so a new host is a config
    # change; this check follows it there instead of grepping this file.
    if "scripts/pack_host_allowlist.json" not in text:
        fail("workflow does not reference scripts/pack_host_allowlist.json")
    if not ALLOWLIST_PATH.is_file():
        fail(f"missing file: {ALLOWLIST_PATH}")
        return
    import json

    try:
        allowlist_hosts = {h["host"] for h in json.loads(ALLOWLIST_PATH.read_text())["hosts"]}
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        fail(f"scripts/pack_host_allowlist.json did not parse as expected: {exc}")
        return
    for host in HOST_ALLOWLIST:
        if host not in allowlist_hosts:
            fail(f"host allow-list missing host: {host}")
    allowlist_text = ALLOWLIST_PATH.read_text()
    if "/releases/" not in allowlist_text:
        fail("host allow-list missing github.com /releases/ path restriction")
    if not FETCH_PACK_PATH.is_file():
        fail(f"missing file: {FETCH_PACK_PATH}")
        return
    fetch_text = FETCH_PACK_PATH.read_text()
    if "redirect" not in fetch_text.lower():
        fail("fetch_pack.py does not appear to re-validate redirects")
    if "is_private" not in fetch_text or "is_loopback" not in fetch_text:
        fail("fetch_pack.py does not appear to reject private/loopback resolved addresses")


def check_size_cap(text):
    if "314572800" not in text:
        fail("300MB cap constant (314572800 bytes) not found")
    if "--max-bytes" not in text:
        fail("fetch_pack.py --max-bytes invocation (during-download cap) not found")
    if not FETCH_PACK_PATH.is_file() or "Content-Length" not in FETCH_PACK_PATH.read_text():
        fail("pre-download Content-Length check not found in fetch_pack.py")


def check_hash_write(text):
    if "sha256sum" not in text:
        fail("sha256 computation (sha256sum) not found")
    if "PACK_HASH_FIELD_ID" not in text:
        fail("Pack Hash field id constant not referenced")
    if "independent of the verdict" not in text:
        fail("no comment documenting the unconditional (always) Pack Hash write")


def check_mep_lint_call(text):
    if "python3 scripts/mep_lint.py" not in text:
        fail("exact 'python3 scripts/mep_lint.py' invocation not found")


def check_claude_action(text):
    if "anthropics/claude-code-action" not in text:
        fail("anthropics/claude-code-action not used")
    if "disallowed_tools" not in text or "Bash" not in text:
        fail("Claude Code Action step does not explicitly disallow Bash")
    lowered = text.lower()
    has_data_word = "data" in lowered
    has_not_instruction = "never" in lowered
    if not (has_data_word and has_not_instruction):
        fail("prompt lacks an explicit data-not-instruction clause")


def check_secret_name_comment(text):
    header = "\n".join(text.splitlines()[:15])
    for secret in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        if secret not in header:
            fail(f"top-of-file comment does not name required secret: {secret}")


def check_catalog_dispatch_gated_on_aceito(text):
    if "community-pack-catalog.yml" not in text:
        fail("no literal reference to community-pack-catalog.yml (dispatch/uses)")
        return
    blocks = [b for b in text.split("\n      - name:") if "community-pack-catalog.yml" in b]
    if not any(any(m in b for m in ACEITO_MARKERS) for b in blocks):
        fail("community-pack-catalog.yml call is not gated on an Aceito* status")


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


CLASSIFY_TOP_LEVEL_REQUIRED = '"required":["verdict","assets","comment"]'
CLASSIFY_RECIPE_FRAGMENT_REQUIRED = '"required":["ops","deps","pack"]'
CLASSIFY_SOURCES_HASH_PROPERTY = '"sources":{"type"'


def _classify_block(text):
    blocks = [b for b in text.split("\n      - name:") if "Classify pack" in b]
    if not blocks:
        fail("Classify pack step not found")
        return None
    return blocks[0]


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


CHECKS = (
    check_ids,
    check_project_number_only,
    check_host_allowlist,
    check_size_cap,
    check_hash_write,
    check_mep_lint_call,
    check_claude_action,
    check_secret_name_comment,
    check_catalog_dispatch_gated_on_aceito,
    check_classify_timeout,
    check_classify_recipe_fragment_required,
    check_classify_top_level_required_unchanged,
    check_classify_schema_no_sources_field,
    check_assemble_recipe_step_present,
    check_assemble_recipe_issue_body_via_gh,
    check_assemble_recipe_runner_temp_handoff,
    check_recipe_status_three_values,
    check_no_github_event_issue,
)


def main():
    text, data = load()
    if text:
        check_workflow_call_inputs(data)
        for check in CHECKS:
            check(text)
    if FAILURES:
        print(f"FAIL ({len(FAILURES)} issue(s)):")
        for msg in FAILURES:
            print(f"  - {msg}")
        return 1
    print("PASS: community-pack-validate.yml structural checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
