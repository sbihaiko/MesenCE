#!/usr/bin/env python3
"""Verifica a proveniência gh project documentada em community-pack-drift-check.yml (AC-5).

Checa, sobre o arquivo real (sem mocks):
  - os fatos CONFIRMADOS ao vivo (IDs do campo Status e do campo Pack Hash,
    via `gh project field-list`) estão documentados com os IDs exatos;
  - o gap de cobertura NÃO CONFIRMADO (nomes de chave JSON por item, porque
    `gh project item-list` devolveu zero itens) está declarado explicitamente,
    não apresentado como fato assentado;
  - qualquer conclusão negativa é qualificada por esse gap (linguagem de
    ressalva, não uma afirmação definitiva);
  - o parsing de item usa lookups defensivos (fallback `//`), não indexação
    direta que quebraria com uma chave ausente.

Uso: python3 scripts/checks/verify_gh_project_provenance_drift.py
"""
import re
import sys
from pathlib import Path

WORKFLOW = Path(".github/workflows/community-pack-drift-check.yml")

STATUS_FIELD_ID = "PVTSSF_lAHOB1MsbM4BhjpNzhge86c"
PACK_HASH_FIELD_ID = "PVTF_lAHOB1MsbM4BhjpNzhge9Is"


def check_confirmed_facts(text, errors):
    if "CONFIRMADO" not in text:
        errors.append("bloco de proveniência não marca nenhum fato como CONFIRMADO")
    if "gh project field-list" not in text:
        errors.append("proveniência não cita 'gh project field-list' como fonte primária")
    if STATUS_FIELD_ID not in text:
        errors.append(f"ID do campo Status ({STATUS_FIELD_ID}) ausente do bloco de proveniência")
    if PACK_HASH_FIELD_ID not in text:
        errors.append(f"ID do campo Pack Hash ({PACK_HASH_FIELD_ID}) ausente do bloco de proveniência")


def check_coverage_gap_disclosed(text, errors):
    if "NÃO CONFIRMADO" not in text:
        errors.append("bloco de proveniência não declara nenhum gap NÃO CONFIRMADO")
    if "gh project item-list" not in text:
        errors.append("gap de cobertura não cita 'gh project item-list' como a chamada que revelou o gap")
    if not re.search(r"zero itens|ZERO itens|totalCount.{0,5}0", text, re.IGNORECASE):
        errors.append("gap de cobertura não menciona que o Project tinha zero itens no momento da spec")
    if "gap de cobertura" not in text:
        errors.append("texto não usa a expressão 'gap de cobertura' para o coverage gap")


def check_negative_conclusion_hedged(text, errors):
    hedges = ["provisória", "não definitiva", "necessariamente provisória"]
    if not any(h in text for h in hedges):
        errors.append(
            "nenhuma conclusão negativa é qualificada como provisória/não definitiva "
            "(deve haver ressalva explícita, não uma afirmação assentada)"
        )


def check_defensive_parsing(text, errors):
    fallback_lines = re.findall(r"jq -r '[^']*//[^']*'", text)
    if len(fallback_lines) < 2:
        errors.append(
            "menos de 2 lookups jq com fallback '//' encontrados - parsing de item "
            "não parece suficientemente defensivo (status e Pack Hash precisam de fallback)"
        )
    if "propositalmente defensivo" not in text and "defensivo" not in text:
        errors.append("comentário não declara explicitamente que o parsing é defensivo")


def main():
    if not WORKFLOW.exists():
        print(f"FAIL: {WORKFLOW} não existe")
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
