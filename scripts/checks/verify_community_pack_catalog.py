#!/usr/bin/env python3
"""AC-6 — community-pack-catalog.yml + generate_community_pack_catalog.py.

Scope of this check (deliberate): only looks at the community-pack-catalog.yml
file ITSELF (must trigger on `workflow_dispatch`, and must not open/reference
`community-pack-validate.yml`) and at the catalog generator script (required
columns + a "Most popular" section labeled as a popularity proxy). The other
half of AC-6 — "called from community-pack-validate.yml when the final
Status is one of the two Aceito* states" — is the responsibility of
community-pack-validate.yml's own checker, not this script.

Usage: python3 scripts/checks/verify_community_pack_catalog.py
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = ROOT / ".github/workflows/community-pack-catalog.yml"
SCRIPT = ROOT / "scripts/generate_community_pack_catalog.py"

REQUIRED_COLUMNS = ["Link", "Game", "Console", "Author", "Category", "Date"]


def _workflow_triggers(data):
    """`on:` becomes the boolean key True under YAML 1.1/PyYAML — cover both cases."""
    return data.get(True, data.get("on"))


def check_workflow(failures):
    if not WORKFLOW.exists():
        failures.append(f"missing file: {WORKFLOW}")
        return
    text = WORKFLOW.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    triggers = _workflow_triggers(data) if isinstance(data, dict) else None
    if not isinstance(triggers, dict) or "workflow_dispatch" not in triggers:
        failures.append("community-pack-catalog.yml must trigger on workflow_dispatch")
    # Deliberately does NOT open/read community-pack-validate.yml here: the
    # "called from community-pack-validate.yml on an Aceito* Status" half of
    # AC-6 is the responsibility of the reusable workflow's own checker. An
    # explanatory comment in community-pack-catalog.yml may mention that
    # file name in prose without violating this scope.


def check_columns(failures, text):
    for col in REQUIRED_COLUMNS:
        if col not in text:
            failures.append(f"generate_community_pack_catalog.py does not reference column {col!r}")


def check_popularity_labeling(failures, text):
    lowered = text.lower()
    if "most popular" not in lowered:
        failures.append("script does not generate the 'Most popular' section")
    if "popularity proxy" not in lowered:
        failures.append("script does not explicitly label 'Most popular' as a popularity proxy")
    if "usage metric" not in lowered:
        failures.append("script does not make explicit that the reaction count is not a real usage metric")
    if "sorted(" not in text or "thumbs_up" not in text:
        failures.append("script does not sort 'Most popular' by reaction count")


def check_script(failures):
    if not SCRIPT.exists():
        failures.append(f"missing file: {SCRIPT}")
        return
    text = SCRIPT.read_text(encoding="utf-8")
    check_columns(failures, text)
    check_popularity_labeling(failures, text)


def main():
    failures = []
    check_workflow(failures)
    check_script(failures)
    if failures:
        print("FAIL: AC-6 (community-pack-catalog.yml / generate_community_pack_catalog.py)")
        for item in failures:
            print(f" - {item}")
        return 1
    print("PASS: AC-6 (community-pack-catalog.yml / generate_community_pack_catalog.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
