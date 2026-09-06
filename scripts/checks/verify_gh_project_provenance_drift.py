#!/usr/bin/env python3
"""Verifies the gh project provenance documented in community-pack-drift-check.yml (AC-5).

Checks, against the real file (no mocks):
  - the CONFIRMED (confirmed live) facts (Status field ID and Pack Hash
    field ID, via `gh project field-list`) are documented with the exact
    IDs;
  - the per-item JSON shape (`.status`, `.content.number`, `Pack Hash`) is
    documented as confirmed live via `gh project item-list` against the
    populated Project (the original spec-time "zero items" coverage gap was
    closed on 2026-09-06 once real items existed to inspect);
  - item parsing uses defensive lookups (`//` fallback), not direct
    indexing that would break on a missing key.

Usage: python3 scripts/checks/verify_gh_project_provenance_drift.py
"""
import re
import sys
from pathlib import Path

WORKFLOW = Path(".github/workflows/community-pack-drift-check.yml")

STATUS_FIELD_ID = "PVTSSF_lAHOB1MsbM4BhjpNzhge86c"
PACK_HASH_FIELD_ID = "PVTF_lAHOB1MsbM4BhjpNzhge9Is"


def check_confirmed_facts(text, errors):
    if "CONFIRMED" not in text:
        errors.append("provenance block does not mark any fact as CONFIRMED")
    if "gh project field-list" not in text:
        errors.append("provenance does not cite 'gh project field-list' as the primary source")
    if STATUS_FIELD_ID not in text:
        errors.append(f"Status field ID ({STATUS_FIELD_ID}) missing from the provenance block")
    if PACK_HASH_FIELD_ID not in text:
        errors.append(f"Pack Hash field ID ({PACK_HASH_FIELD_ID}) missing from the provenance block")


def check_item_shape_confirmed(text, errors):
    if "gh project item-list" not in text:
        errors.append("provenance does not cite 'gh project item-list' as the source for the per-item shape")
    if not re.search(r"Per-item JSON shape.*confirmed live", text, re.IGNORECASE | re.DOTALL):
        errors.append("per-item JSON shape is not documented as confirmed live against the populated Project")
    for key in (".status", ".content.number", "Pack Hash"):
        if key not in text:
            errors.append(f"confirmed per-item key {key!r} missing from the provenance block")


def check_defensive_parsing(text, errors):
    fallback_lines = re.findall(r"jq -r '[^']*//[^']*'", text)
    if len(fallback_lines) < 2:
        errors.append(
            "fewer than 2 jq lookups with a '//' fallback found - item parsing "
            "does not look defensive enough (status and Pack Hash need a fallback)"
        )
    if "deliberately defensive" not in text and "defensive" not in text:
        errors.append("comment does not explicitly state that the parsing is defensive")


def main():
    if not WORKFLOW.exists():
        print(f"FAIL: {WORKFLOW} does not exist")
        return 1

    text = WORKFLOW.read_text(encoding="utf-8")
    errors = []
    check_confirmed_facts(text, errors)
    check_item_shape_confirmed(text, errors)
    check_defensive_parsing(text, errors)

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1

    print(f"PASS: {WORKFLOW} - confirmed field IDs, confirmed per-item shape, "
          "and defensive jq lookups all documented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
