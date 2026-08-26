#!/usr/bin/env python3
"""AC-6 — community-pack-catalog.yml + generate_community_pack_catalog.py.

Escopo desta checagem (deliberado): olha só para o PRÓPRIO arquivo
`community-pack-catalog.yml` (deve disparar em `workflow_dispatch`, e não
deve abrir/referenciar `community-pack-validate.yml`) e para o script
gerador do catálogo (colunas obrigatórias + seção "Mais populares" rotulada
como proxy de popularidade). A outra metade do AC-6 — "chamado a partir de
community-pack-validate.yml quando o Status final é um dos dois estados
Aceito*" — é responsabilidade do checker do próprio
community-pack-validate.yml, não deste script.

Uso: python3 scripts/checks/verify_community_pack_catalog.py
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = ROOT / ".github/workflows/community-pack-catalog.yml"
SCRIPT = ROOT / "scripts/generate_community_pack_catalog.py"

REQUIRED_COLUMNS = ["Link", "Jogo", "Console", "Autor", "Categoria", "Data"]


def _workflow_triggers(data):
    """`on:` vira chave booleana True em YAML 1.1/PyYAML — cobre os dois casos."""
    return data.get(True, data.get("on"))


def check_workflow(failures):
    if not WORKFLOW.exists():
        failures.append(f"arquivo ausente: {WORKFLOW}")
        return
    text = WORKFLOW.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    triggers = _workflow_triggers(data) if isinstance(data, dict) else None
    if not isinstance(triggers, dict) or "workflow_dispatch" not in triggers:
        failures.append("community-pack-catalog.yml precisa disparar em workflow_dispatch")
    # Deliberadamente NÃO abrimos/lemos community-pack-validate.yml aqui: a
    # metade "chamado a partir de community-pack-validate.yml no Status
    # Aceito*" do AC-6 é responsabilidade do checker do próprio workflow
    # reutilizável. Um comentário explicativo em community-pack-catalog.yml
    # pode mencionar esse nome de arquivo em prosa sem violar esse escopo.


def check_columns(failures, text):
    for col in REQUIRED_COLUMNS:
        if col not in text:
            failures.append(f"generate_community_pack_catalog.py não referencia a coluna {col!r}")


def check_popularity_labeling(failures, text):
    lowered = text.lower()
    if "mais populares" not in lowered:
        failures.append("script não gera a seção 'Mais populares'")
    if "proxy de popularidade" not in lowered:
        failures.append("script não rotula 'Mais populares' explicitamente como proxy de popularidade")
    if "métrica real de uso" not in lowered and "not a usage metric" not in lowered:
        failures.append("script não deixa explícito que a contagem de reações não é uma métrica real de uso")
    if "sorted(" not in text or "thumbs_up" not in text:
        failures.append("script não ordena 'Mais populares' por contagem de reação")


def check_script(failures):
    if not SCRIPT.exists():
        failures.append(f"arquivo ausente: {SCRIPT}")
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
