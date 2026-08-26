#!/usr/bin/env python3
"""Verifica community-pack-drift-check.yml (AC-4).

Checa, sobre o arquivo real (sem mocks):
  - triggers `schedule` (com `cron`) e `workflow_dispatch`;
  - a invocação exata `gh project item-list 3 --owner sbihaiko`;
  - a pré-checagem de hash usando só `curl` + `sha256sum` (sem chamar o
    Claude Code Action nesta etapa);
  - a chamada condicional (só em caso de mismatch) ao workflow reutilizável,
    identificada de forma literal por `uses:` + `mode: revalidate` — nunca
    resolvendo/abrindo community-pack-validate.yml.

Uso: python3 scripts/checks/verify_community_pack_drift_check_workflow.py
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
    # `on:` é lida pelo PyYAML (YAML 1.1) como a chave booleana True, não a
    # string 'on' - checagem estrutural precisa considerar isso.
    triggers = data.get("on", data.get(True))
    if not isinstance(triggers, dict):
        errors.append("bloco 'on:' ausente ou não é um mapeamento")
        return
    if "schedule" not in triggers or not triggers["schedule"]:
        errors.append("trigger 'schedule' ausente")
    elif not any("cron" in entry for entry in triggers["schedule"]):
        errors.append("trigger 'schedule' sem entrada 'cron'")
    if "workflow_dispatch" not in triggers:
        errors.append("trigger 'workflow_dispatch' ausente")


def check_item_list_invocation(text, errors):
    if "gh project item-list 3 --owner sbihaiko" not in text:
        errors.append(
            "invocação exata 'gh project item-list 3 --owner sbihaiko' não encontrada"
        )


def check_curl_sha256_precheck(text, errors):
    if "curl" not in text:
        errors.append("pré-checagem sem 'curl'")
    if "sha256sum" not in text:
        errors.append("pré-checagem sem 'sha256sum'")
    if re.search(r"claude-code-action|anthropics/claude", text):
        errors.append(
            "pré-checagem de drift não deve invocar o Claude Code Action "
            "(deve usar só curl+sha256sum)"
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
            "nenhum job com 'uses: .../community-pack-validate.yml' encontrado"
        )
        return
    mode = job.get("with", {}).get("mode", "")
    if "revalidate" not in str(mode):
        errors.append("job que chama o workflow reutilizável não usa mode: revalidate")
    if "if" not in job:
        errors.append(
            "chamada ao workflow reutilizável não é condicional (falta 'if:' "
            "amarrado ao resultado do diff de mismatch)"
        )


def main():
    if not WORKFLOW.exists():
        print(f"FAIL: {WORKFLOW} não existe")
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
