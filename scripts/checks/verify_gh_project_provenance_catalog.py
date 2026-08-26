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

Uso: python3 scripts/checks/verify_gh_project_provenance_catalog.py
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
        failures.append(f"comentário não cita a chamada primária confirmada ({CONFIRMED_CALL!r})")
    for field_id in CONFIRMED_FIELD_IDS:
        if field_id not in text:
            failures.append(f"comentário não confirma o field id {field_id!r} contra a API real")
    if "CONFIRMA" not in text and "CONFIRMED" not in text.upper():
        failures.append("comentário não usa uma marcação explícita de fato CONFIRMADO")


def check_coverage_gap(failures, text):
    if GAP_CALL not in text:
        failures.append(f"comentário não cita a chamada que expõe o gap ({GAP_CALL!r})")
    lowered = text.lower()
    if "coverage gap" not in lowered:
        failures.append("comentário não rotula explicitamente o gap como 'coverage gap'")
    if "zero itens" not in lowered and "zero items" not in lowered and '"totalcount":0' not in lowered:
        failures.append("comentário não documenta que o Project tinha zero itens no momento da escrita")
    if "qualificada" not in lowered and "qualified" not in lowered:
        failures.append("comentário não deixa explícito que conclusões negativas são qualificadas pelo gap")


def check_defensive_parsing(failures, text):
    lowered = text.lower()
    if "defensiv" not in lowered and "defensive" not in lowered:
        failures.append("comentário não descreve o parsing como defensivo")
    if "não-crash" not in lowered and "non-crash" not in lowered and "not crash" not in lowered:
        failures.append("comentário não deixa explícito que o parsing não deve crashar em chave inesperada")
    dict_get_calls = re.findall(r"\.get\(", text)
    if len(dict_get_calls) < 3:
        failures.append("parsing de item do Project não usa lookups defensivos (dict.get) suficientes")


def main():
    if not SCRIPT.exists():
        print(f"FAIL: arquivo ausente: {SCRIPT}")
        return 1
    text = SCRIPT.read_text(encoding="utf-8")
    failures = []
    check_confirmed_facts(failures, text)
    check_coverage_gap(failures, text)
    check_defensive_parsing(failures, text)
    if failures:
        print("FAIL: AC-7 (provenance/coverage-gap do catalog script)")
        for item in failures:
            print(f" - {item}")
        return 1
    print("PASS: AC-7 (provenance/coverage-gap do catalog script)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
