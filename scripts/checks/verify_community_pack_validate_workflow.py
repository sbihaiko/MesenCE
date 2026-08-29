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

The 28+ checks that made this file grow well past the project's 200-line
guardrail are split into topic modules under
scripts/checks/community_pack_validate/ (ADR-0138 Clarification §23,
F6.2c): general, classify, autofix, assemble_recipe, recipe_gate,
apply_verdict, mep_meta. This file stays the sole invocation entry point —
it only loads
the workflow file, runs the workflow_call-inputs check that needs the
parsed YAML, assembles CHECKS from the topic modules' functions, and
reports failures.

Usage: python3 scripts/checks/verify_community_pack_validate_workflow.py
"""
import sys
from pathlib import Path

import yaml

from community_pack_validate import (
    apply_verdict,
    assemble_recipe,
    autofix,
    classify,
    general,
    mep_meta,
    recipe_gate,
)
from community_pack_validate._shared import FAILURES, fail

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github" / "workflows" / "community-pack-validate.yml"
)


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


CHECKS = (
    general.check_ids,
    general.check_project_number_only,
    general.check_host_allowlist,
    general.check_size_cap,
    general.check_hash_write,
    general.check_mep_lint_call,
    general.check_claude_action,
    general.check_prompt_file_data_not_instruction,
    general.check_secret_name_comment,
    general.check_catalog_dispatch_gated_on_aceito,
    classify.check_classify_timeout,
    classify.check_classify_recipe_fragment_required,
    classify.check_classify_top_level_required_unchanged,
    classify.check_classify_schema_no_sources_field,
    classify.check_classify_step_references_prepare_outputs,
    classify.check_prepare_classify_prompt_renders_md,
    classify.check_prompt_file_markers,
    autofix.check_autofix_step_references_prepare_outputs,
    autofix.check_prepare_autofix_prompt_renders_md,
    autofix.check_autofix_prompt_file_markers,
    autofix.check_autofix_prompt_data_not_instruction,
    assemble_recipe.check_assemble_recipe_step_present,
    assemble_recipe.check_assemble_recipe_issue_body_via_gh,
    assemble_recipe.check_assemble_recipe_runner_temp_handoff,
    assemble_recipe.check_recipe_status_three_values,
    recipe_gate.check_recipe_gate_step_present_and_gated,
    recipe_gate.check_recipe_gate_never_uses_inverted_condition,
    recipe_gate.check_no_github_event_issue,
    apply_verdict.check_apply_verdict_downgrade_expression,
    apply_verdict.check_apply_verdict_external_label_branch,
    apply_verdict.check_apply_verdict_exposes_outputs,
    apply_verdict.check_apply_verdict_kind_matches_mei_rules_status_to_kind,
    mep_meta.check_mep_meta_step_present_and_not_gated_on_recipe_status,
    mep_meta.check_mep_meta_find_then_patch,
    mep_meta.check_mep_meta_marker_in_comment_body,
    mep_meta.check_mep_meta_provenance_line,
    mep_meta.check_mep_meta_body_built_via_python_json,
    mep_meta.check_mep_meta_omits_deps_and_recipe_hash_when_absent,
    mep_meta.check_mep_meta_fence_not_hardcoded,
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
