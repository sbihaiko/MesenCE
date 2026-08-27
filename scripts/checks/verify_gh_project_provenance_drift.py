#!/usr/bin/env python3
"""Verifies the gh project provenance documented in community-pack-drift-check.yml (AC-5).

Checks, against the real file (no mocks):
  - the CONFIRMED (confirmed live) facts (Status field ID and Pack Hash
    field ID, via `gh project field-list`) are documented with the exact
    IDs;
  - the UNCONFIRMED coverage gap (per-item JSON key names, because
    `gh project item-list` returned zero items) is explicitly declared,
    not presented as a settled fact;
  - any negative conclusion is qualified by that gap (hedged language, not
    a definitive statement);
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


def check_coverage_gap_disclosed(text, errors):
    if "UNCONFIRMED" not in text:
        errors.append("provenance block does not declare any UNCONFIRMED gap")
    if "gh project item-list" not in text:
        errors.append("coverage gap does not cite 'gh project item-list' as the call that revealed the gap")
    if not re.search(r"zero items|ZERO items|totalCount.{0,5}0", text, re.IGNORECASE):
        errors.append("coverage gap does not mention that the Project had zero items at spec time")
    if "coverage gap" not in text:
        errors.append("text does not use the phrase 'coverage gap' for the coverage gap")


def check_negative_conclusion_hedged(text, errors):
    hedges = ["provisional", "not definitive", "necessarily provisional"]
    if not any(h in text for h in hedges):
        errors.append(
            "no negative conclusion is qualified as provisional/non-definitive "
            "(there must be an explicit hedge, not a settled statement)"
        )


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
    check_coverage_gap_disclosed(text, errors)
    check_negative_conclusion_hedged(text, errors)
    check_defensive_parsing(text, errors)

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1

    print(f"PASS: {WORKFLOW} - confirmed field IDs, disclosed item-list coverage gap, "
          "hedged negative conclusions, and defensive jq lookups all documented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
