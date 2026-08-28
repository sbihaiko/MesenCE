#!/usr/bin/env python3
"""Verifies .github/workflows/community-pack-submitted.yml (AC-3, F6.0).

Checks only the trigger file itself:
  - fires on issues: [opened, edited] filtered by the community-pack label;
  - fires on issue_comment: [created] whose body is EXACTLY "/revalidate"
    on an issue with that label;
  - calls the reusable community-pack-validate.yml workflow with
    mode: submit (issue triggers) and mode: revalidate (the /revalidate
    comment trigger);
  - concurrency cancel-in-progress is gated on `issues` events so a
    verdict comment cannot cancel the run that posted it (F6.0, ADR-0138).

Deliberately does NOT open or resolve community-pack-validate.yml: the
reusable-workflow call is checked only as a literal string match
("uses: .../community-pack-validate.yml" and "mode: submit" /
"mode: revalidate"), so this check stays independent of whoever is
writing that other file.

Usage: python3 scripts/checks/verify_community_pack_submitted_workflow.py
Output: PASS/FAIL per check, exit 0 if all pass, 1 otherwise.
"""
import sys
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/community-pack-submitted.yml")

# Exact expression F6.0 requires: cancel in-flight runs for a newer
# issues opened/edited trigger, but never for issue_comment (the verdict
# comment would otherwise cancel the catalog dispatch).
CANCEL_IN_PROGRESS_EXPR = "cancel-in-progress: ${{ github.event_name == 'issues' }}"


def load_workflow(path: Path):
    text = path.read_text(encoding="utf-8")
    # PyYAML parses the bare "on:" key as the boolean True under the
    # default SafeLoader resolver; grab both spellings defensively so a
    # parser/version difference doesn't crash this check silently.
    data = yaml.safe_load(text)
    return text, data


def get_triggers(data):
    for key in ("on", True):
        if key in data:
            return data[key]
    return None


def check_issues_trigger(triggers):
    issues = triggers.get("issues") if isinstance(triggers, dict) else None
    if not isinstance(issues, dict):
        return False, "trigger 'issues' missing or not a mapping"
    types = issues.get("types") or []
    missing = [t for t in ("opened", "edited") if t not in types]
    if missing:
        return False, f"issues.types does not include {missing}"
    return True, "issues: types includes opened and edited"


def check_issue_comment_trigger(triggers):
    ic = triggers.get("issue_comment") if isinstance(triggers, dict) else None
    if not isinstance(ic, dict):
        return False, "trigger 'issue_comment' missing or not a mapping"
    types = ic.get("types") or []
    if "created" not in types:
        return False, "issue_comment.types does not include 'created'"
    return True, "issue_comment: types includes created"


def check_label_filter(text):
    if "community-pack" not in text:
        return False, "no literal reference to the 'community-pack' label"
    if "contains(github.event.issue.labels" not in text:
        return False, "no contains(...) filter over issue.labels"
    return True, "condition references the community-pack label via contains(...)"


def check_exact_revalidate(text):
    needle = "github.event.comment.body == '/revalidate'"
    if needle not in text:
        return False, f"exact-equality condition missing: {needle!r}"
    return True, "exact comparison \"== '/revalidate'\" found"


def check_reusable_call(text, mode_value):
    uses_needle = "uses: ./.github/workflows/community-pack-validate.yml"
    if uses_needle not in text:
        return False, f"reusable-workflow call missing: {uses_needle!r}"
    mode_needle = f"mode: {mode_value}"
    if mode_needle not in text:
        return False, f"literal missing: {mode_needle!r}"
    return True, f"found reusable 'uses:' and '{mode_needle}'"


def check_cancel_in_progress(text, data):
    if CANCEL_IN_PROGRESS_EXPR not in text:
        return False, (
            "concurrency cancel-in-progress is not gated on issues events: "
            f"expected {CANCEL_IN_PROGRESS_EXPR!r}"
        )
    # Inspect the parsed value, not a raw-text grep: comments in this file
    # mention the old `cancel-in-progress: true` as the bug being fixed.
    concurrency = data.get("concurrency") if isinstance(data, dict) else None
    if not isinstance(concurrency, dict):
        return False, "concurrency block missing or not a mapping"
    cip = concurrency.get("cancel-in-progress")
    if cip is True:
        return False, (
            "unconditional cancel-in-progress: true would cancel the run "
            "when the verdict comment fires issue_comment (F6.0)"
        )
    expected = "${{ github.event_name == 'issues' }}"
    if cip != expected:
        return False, f"cancel-in-progress is {cip!r}, expected {expected!r}"
    return True, "cancel-in-progress only for issues events (issue_comment does not cancel)"


def run_checks(text, data):
    triggers = get_triggers(data)
    results = []
    if triggers is None:
        results.append((False, "'on:' key missing from the workflow"))
        return results
    results.append(check_issues_trigger(triggers))
    results.append(check_issue_comment_trigger(triggers))
    results.append(check_label_filter(text))
    results.append(check_exact_revalidate(text))
    results.append(check_reusable_call(text, "submit"))
    results.append(check_reusable_call(text, "revalidate"))
    results.append(check_cancel_in_progress(text, data))
    return results


def main():
    if not WORKFLOW_PATH.exists():
        print(f"FAIL: {WORKFLOW_PATH} does not exist")
        return 1

    text, data = load_workflow(WORKFLOW_PATH)
    if not isinstance(data, dict):
        print("FAIL: YAML root is not a mapping")
        return 1

    results = run_checks(text, data)
    ok = True
    for passed, message in results:
        status = "PASS" if passed else "FAIL"
        print(f"{status}: {message}")
        ok = ok and passed

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
