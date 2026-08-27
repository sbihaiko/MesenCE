#!/usr/bin/env python3
"""Verifies community-pack-drift-check.yml (AC-4).

Checks, against the real file (no mocks):
  - `schedule` (with `cron`) and `workflow_dispatch` triggers;
  - the exact invocation `gh project item-list 3 --owner sbihaiko`;
  - the hash pre-check using only `curl` + `sha256sum` (without calling the
    Claude Code Action at this step);
  - the conditional call (only on mismatch) to the reusable workflow,
    identified literally by `uses:` + `mode: revalidate` — never
    resolving/opening community-pack-validate.yml.

Usage: python3 scripts/checks/verify_community_pack_drift_check_workflow.py
"""
import re
import sys
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/community-pack-drift-check.yml")


def load(path):
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return text, data


def check_triggers(data, errors):
    # `on:` is read by PyYAML (YAML 1.1) as the boolean key True, not the
    # string 'on' - the structural check needs to account for that.
    triggers = data.get("on", data.get(True))
    if not isinstance(triggers, dict):
        errors.append("'on:' block missing or not a mapping")
        return
    if "schedule" not in triggers or not triggers["schedule"]:
        errors.append("'schedule' trigger missing")
    elif not any("cron" in entry for entry in triggers["schedule"]):
        errors.append("'schedule' trigger has no 'cron' entry")
    if "workflow_dispatch" not in triggers:
        errors.append("'workflow_dispatch' trigger missing")


def check_item_list_invocation(text, errors):
    if "gh project item-list 3 --owner sbihaiko" not in text:
        errors.append(
            "exact invocation 'gh project item-list 3 --owner sbihaiko' not found"
        )


def check_curl_sha256_precheck(text, errors):
    if "curl" not in text:
        errors.append("pre-check missing 'curl'")
    if "sha256sum" not in text:
        errors.append("pre-check missing 'sha256sum'")
    if re.search(r"claude-code-action|anthropics/claude", text):
        errors.append(
            "the drift pre-check must not invoke the Claude Code Action "
            "(must use only curl+sha256sum)"
        )


def find_reusable_call_job(data):
    jobs = data.get("jobs", {})
    for job in jobs.values():
        uses = job.get("uses", "")
        if isinstance(uses, str) and "community-pack-validate.yml" in uses:
            return job
    return None


def check_conditional_revalidate_call(data, errors):
    job = find_reusable_call_job(data)
    if job is None:
        errors.append(
            "no job with 'uses: .../community-pack-validate.yml' found"
        )
        return
    mode = job.get("with", {}).get("mode", "")
    if "revalidate" not in str(mode):
        errors.append("job that calls the reusable workflow does not use mode: revalidate")
    if "if" not in job:
        errors.append(
            "call to the reusable workflow is not conditional (missing 'if:' "
            "tied to the mismatch diff result)"
        )


def main():
    if not WORKFLOW.exists():
        print(f"FAIL: {WORKFLOW} does not exist")
        return 1

    text, data = load(WORKFLOW)
    errors = []
    check_triggers(data, errors)
    check_item_list_invocation(text, errors)
    check_curl_sha256_precheck(text, errors)
    check_conditional_revalidate_call(data, errors)

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1

    print(f"PASS: {WORKFLOW} - triggers, gh invocation, curl+sha256sum precheck, "
          "conditional mode:revalidate call all present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
