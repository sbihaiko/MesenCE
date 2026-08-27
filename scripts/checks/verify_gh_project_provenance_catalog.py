#!/usr/bin/env python3
"""AC-7 — provenance/coverage-gap disclosure in the catalog script's own
`gh project item-list` parsing.

Same requirement as AC-5 (scripts/checks/verify_gh_project_provenance_drift.py,
owned by the drift-check task), scoped here to
scripts/generate_community_pack_catalog.py: the code comment must state which
`gh project` field/id facts were confirmed via a live primary-source `gh`
call (the Status and Pack Hash field ids, via `gh project field-list`) versus
which per-item JSON key names remain an explicit, unconfirmed coverage gap
(the Project held zero items at spec/write time, per a live
`gh project item-list` call — a gap in the datastore's population, not
merely in a cached view), and the item-parsing code must use defensive,
non-crashing lookups rather than direct indexing on an assumed key path.

NOTE: scripts/generate_community_pack_catalog.py's own docstring was already
in English by the time this checker was translated, so the matched string
literals below are English-only (no pt-BR fallback needed here, unlike the
sibling check for community-pack-drift-check.yml).

Usage: python3 scripts/checks/verify_gh_project_provenance_catalog.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts/generate_community_pack_catalog.py"

CONFIRMED_FIELD_IDS = ["PVTSSF_lAHOB1MsbM4BhjpNzhge86c", "PVTF_lAHOB1MsbM4BhjpNzhge9Is"]
CONFIRMED_CALL = "gh project field-list"
GAP_CALL = "gh project item-list"


def check_confirmed_facts(failures, text):
    if CONFIRMED_CALL not in text:
        failures.append(f"comment does not cite the confirmed primary-source call ({CONFIRMED_CALL!r})")
    for field_id in CONFIRMED_FIELD_IDS:
        if field_id not in text:
            failures.append(f"comment does not confirm field id {field_id!r} against the real API")
    if "CONFIRMED" not in text.upper():
        failures.append("comment does not use an explicit CONFIRMED fact marker")


def check_coverage_gap(failures, text):
    if GAP_CALL not in text:
        failures.append(f"comment does not cite the call that exposes the gap ({GAP_CALL!r})")
    lowered = text.lower()
    if "coverage gap" not in lowered:
        failures.append("comment does not explicitly label the gap as a 'coverage gap'")
    if "zero items" not in lowered and '"totalcount":0' not in lowered:
        failures.append("comment does not document that the Project had zero items at write time")
    if "qualified" not in lowered:
        failures.append("comment does not make explicit that negative conclusions are qualified by the gap")


def check_defensive_parsing(failures, text):
    lowered = text.lower()
    if "defensiv" not in lowered:
        failures.append("comment does not describe the parsing as defensive")
    if "non-crash" not in lowered and "not crash" not in lowered:
        failures.append("comment does not make explicit that parsing must not crash on an unexpected key")
    dict_get_calls = re.findall(r"\.get\(", text)
    if len(dict_get_calls) < 3:
        failures.append("Project item parsing does not use enough defensive lookups (dict.get)")


def main():
    if not SCRIPT.exists():
        print(f"FAIL: missing file: {SCRIPT}")
        return 1
    text = SCRIPT.read_text(encoding="utf-8")
    failures = []
    check_confirmed_facts(failures, text)
    check_coverage_gap(failures, text)
    check_defensive_parsing(failures, text)
    if failures:
        print("FAIL: AC-7 (catalog script provenance/coverage-gap)")
        for item in failures:
            print(f" - {item}")
        return 1
    print("PASS: AC-7 (catalog script provenance/coverage-gap)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
