#!/usr/bin/env python3
"""
Verifica .github/workflows/community-pack-submitted.yml (AC-3).

Checa apenas o arquivo trigger em si:
  - dispara em issues: [opened, edited] filtrado pela label community-pack;
  - dispara em issue_comment: [created] com corpo EXATAMENTE "/revalidate"
    numa issue com essa label;
  - chama o workflow reusavel community-pack-validate.yml com
    mode: submit (para os gatilhos de issue) e mode: revalidate (para o
    gatilho de comentario /revalidate).

Deliberadamente NAO abre nem resolve community-pack-validate.yml: a
chamada ao workflow reusavel e checada apenas como correspondencia
literal de string ("uses: .../community-pack-validate.yml" e
"mode: submit" / "mode: revalidate"), para que este check permaneca
paralelo/independente de quem estiver escrevendo aquele outro arquivo.

Uso: python3 scripts/checks/verify_community_pack_submitted_workflow.py
Saida: PASS/FAIL por checagem, exit 0 se tudo passar, 1 caso contrario.
"""
import sys
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/community-pack-submitted.yml")


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
        return False, "trigger 'issues' ausente ou nao e um mapeamento"
    types = issues.get("types") or []
    missing = [t for t in ("opened", "edited") if t not in types]
    if missing:
        return False, f"issues.types nao inclui {missing}"
    return True, "issues: types inclui opened e edited"


def check_issue_comment_trigger(triggers):
    ic = triggers.get("issue_comment") if isinstance(triggers, dict) else None
    if not isinstance(ic, dict):
        return False, "trigger 'issue_comment' ausente ou nao e um mapeamento"
    types = ic.get("types") or []
    if "created" not in types:
        return False, "issue_comment.types nao inclui 'created'"
    return True, "issue_comment: types inclui created"


def check_label_filter(text):
    if "community-pack" not in text:
        return False, "nenhuma referencia literal a label 'community-pack'"
    if "contains(github.event.issue.labels" not in text:
        return False, "nenhum filtro contains(...) sobre issue.labels"
    return True, "condicao referencia a label community-pack via contains(...)"


def check_exact_revalidate(text):
    needle = "github.event.comment.body == '/revalidate'"
    if needle not in text:
        return False, f"condicao de igualdade exata ausente: {needle!r}"
    return True, "comparacao exata '== '/revalidate'' encontrada"


def check_reusable_call(text, mode_value):
    uses_needle = "uses: ./.github/workflows/community-pack-validate.yml"
    if uses_needle not in text:
        return False, f"chamada reusavel ausente: {uses_needle!r}"
    mode_needle = f"mode: {mode_value}"
    if mode_needle not in text:
        return False, f"literal ausente: {mode_needle!r}"
    return True, f"encontrado 'uses:' reusavel e '{mode_needle}'"


def run_checks(text, data):
    triggers = get_triggers(data)
    results = []
    if triggers is None:
        results.append((False, "chave 'on:' ausente do workflow"))
        return results
    results.append(check_issues_trigger(triggers))
    results.append(check_issue_comment_trigger(triggers))
    results.append(check_label_filter(text))
    results.append(check_exact_revalidate(text))
    results.append(check_reusable_call(text, "submit"))
    results.append(check_reusable_call(text, "revalidate"))
    return results


def main():
    if not WORKFLOW_PATH.exists():
        print(f"FAIL: {WORKFLOW_PATH} nao existe")
        return 1

    text, data = load_workflow(WORKFLOW_PATH)
    if not isinstance(data, dict):
        print("FAIL: YAML raiz nao e um mapeamento")
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
