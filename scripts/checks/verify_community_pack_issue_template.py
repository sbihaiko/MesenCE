#!/usr/bin/env python3
"""Verifica .github/ISSUE_TEMPLATE/community-pack.yml (AC-1).

Confere que o arquivo é um GitHub Issue Form (não issue de texto livre) com:
- campo de link do pack (URL)
- campo jogo/ROM alvo + região
- dropdown de console (NES/SNES/GB/GBC/SMS/outro)
- campo autor/créditos
- checkbox obrigatório de confirmação de direitos
- campo de descrição opcional
- labels: [community-pack]
- link para docs/hd-pack-authoring.md

Sem dependências além de PyYAML (já usado por outros checks do repo).
"""
import pathlib
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "community-pack.yml"

CONSOLE_OPTIONS = {"nes", "snes", "gb", "gbc", "sms", "outro"}


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def load_template():
    if not TEMPLATE_PATH.is_file():
        fail(f"arquivo não encontrado: {TEMPLATE_PATH}")
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        fail(f"YAML inválido em {TEMPLATE_PATH}: {exc}")
    if not isinstance(data, dict):
        fail("documento raiz não é um mapeamento YAML")
    return data, text


def check_top_level(data):
    if "body" not in data or not isinstance(data["body"], list):
        fail("chave 'body' ausente ou não é uma lista (não é um Issue Form)")
    labels = data.get("labels")
    if labels != ["community-pack"]:
        fail(f"labels deve ser ['community-pack'], encontrado: {labels!r}")


def check_doc_link(text):
    if "docs/hd-pack-authoring.md" not in text:
        fail("nenhum link para docs/hd-pack-authoring.md encontrado no template")


def find_fields(body):
    by_type = {}
    for element in body:
        if not isinstance(element, dict):
            continue
        etype = element.get("type")
        by_type.setdefault(etype, []).append(element)
    return by_type


def is_required(element):
    validations = element.get("validations") or {}
    return bool(validations.get("required"))


def check_pack_link(inputs):
    matches = [
        e
        for e in inputs
        if "link" in str(e.get("attributes", {}).get("label", "")).lower()
        or "url" in str(e.get("id", "")).lower()
        or "link" in str(e.get("id", "")).lower()
    ]
    if not matches:
        fail("nenhum campo 'input' de link do pack encontrado")
    if not any(is_required(e) for e in matches):
        fail("campo de link do pack não é obrigatório")


def check_rom_target(inputs):
    matches = [
        e
        for e in inputs
        if "rom" in str(e.get("id", "")).lower()
        or "jogo" in str(e.get("attributes", {}).get("label", "")).lower()
    ]
    if not matches:
        fail("nenhum campo 'input' de jogo/ROM alvo + região encontrado")


def check_console_dropdown(dropdowns):
    if not dropdowns:
        fail("nenhum campo 'dropdown' de console encontrado")
    for dropdown in dropdowns:
        options = dropdown.get("attributes", {}).get("options") or []
        normalized = {str(o).strip().lower() for o in options}
        if CONSOLE_OPTIONS.issubset(normalized):
            return
    fail(f"nenhum dropdown cobre as opções esperadas {sorted(CONSOLE_OPTIONS)}")


def check_author_field(inputs):
    matches = [
        e
        for e in inputs
        if "autor" in str(e.get("id", "")).lower()
        or "credit" in str(e.get("id", "")).lower()
    ]
    if not matches:
        fail("nenhum campo 'input' de autor/créditos encontrado")


def check_rights_checkbox(checkboxes):
    if not checkboxes:
        fail("nenhum campo 'checkboxes' encontrado")
    for cb in checkboxes:
        options = cb.get("attributes", {}).get("options") or []
        for opt in options:
            if isinstance(opt, dict) and opt.get("required") is True:
                return
    fail("nenhuma opção de checkbox obrigatória de confirmação de direitos encontrada")


def check_optional_description(textareas):
    matches = [e for e in textareas if "descri" in str(e.get("id", "")).lower()]
    if not matches:
        fail("nenhum campo 'textarea' de descrição encontrado")
    for textarea in matches:
        validations = textarea.get("validations") or {}
        if validations.get("required") is True:
            fail("campo de descrição deveria ser opcional, mas está marcado required")


def main():
    data, text = load_template()
    check_top_level(data)
    check_doc_link(text)

    by_type = find_fields(data["body"])
    check_pack_link(by_type.get("input", []))
    check_rom_target(by_type.get("input", []))
    check_console_dropdown(by_type.get("dropdown", []))
    check_author_field(by_type.get("input", []))
    check_rights_checkbox(by_type.get("checkboxes", []))
    check_optional_description(by_type.get("textarea", []))

    print("PASS: community-pack.yml é um Issue Form válido com todos os campos exigidos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
