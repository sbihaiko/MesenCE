#!/usr/bin/env python3
"""Verifies .github/ISSUE_TEMPLATE/community-pack.yml (AC-1).

Confirms that the file is a GitHub Issue Form (not a free-text issue) with:
- pack link field (URL)
- target game/ROM + region field
- console dropdown (NES/GB/GBC/SMS/Other — no SNES: not a product console on main)
- author/credits field
- optional description field
- labels: [community-pack]
- link to docs/hd-pack-authoring.md

No dependencies beyond PyYAML (already used by other checks in the repo).
"""
import pathlib
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "community-pack.yml"

CONSOLE_OPTIONS = {"nes", "gb", "gbc", "sms", "other"}


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def load_template():
    if not TEMPLATE_PATH.is_file():
        fail(f"file not found: {TEMPLATE_PATH}")
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        fail(f"invalid YAML in {TEMPLATE_PATH}: {exc}")
    if not isinstance(data, dict):
        fail("root document is not a YAML mapping")
    return data, text


def check_top_level(data):
    if "body" not in data or not isinstance(data["body"], list):
        fail("'body' key missing or not a list (not an Issue Form)")
    labels = data.get("labels")
    if labels != ["community-pack"]:
        fail(f"labels must be ['community-pack'], found: {labels!r}")


def check_doc_link(text):
    if "docs/hd-pack-authoring.md" not in text:
        fail("no link to docs/hd-pack-authoring.md found in the template")


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
        fail("no pack-link 'input' field found")
    if not any(is_required(e) for e in matches):
        fail("pack-link field is not required")


def check_rom_target(inputs):
    matches = [
        e
        for e in inputs
        if "rom" in str(e.get("id", "")).lower()
        or "game" in str(e.get("attributes", {}).get("label", "")).lower()
    ]
    if not matches:
        fail("no target game/ROM + region 'input' field found")


def check_console_dropdown(dropdowns):
    if not dropdowns:
        fail("no console 'dropdown' field found")
    for dropdown in dropdowns:
        options = dropdown.get("attributes", {}).get("options") or []
        normalized = {str(o).strip().lower() for o in options}
        if CONSOLE_OPTIONS.issubset(normalized):
            return
    fail(f"no dropdown covers the expected options {sorted(CONSOLE_OPTIONS)}")


def check_author_field(inputs):
    matches = [
        e
        for e in inputs
        if "author" in str(e.get("id", "")).lower()
        or "credit" in str(e.get("id", "")).lower()
    ]
    if not matches:
        fail("no author/credits 'input' field found")



def check_optional_description(textareas):
    matches = [e for e in textareas if "descri" in str(e.get("id", "")).lower()]
    if not matches:
        fail("no description 'textarea' field found")
    for textarea in matches:
        validations = textarea.get("validations") or {}
        if validations.get("required") is True:
            fail("description field should be optional, but is marked required")


def main():
    data, text = load_template()
    check_top_level(data)
    check_doc_link(text)

    by_type = find_fields(data["body"])
    check_pack_link(by_type.get("input", []))
    check_rom_target(by_type.get("input", []))
    check_console_dropdown(by_type.get("dropdown", []))
    check_author_field(by_type.get("input", []))
    check_optional_description(by_type.get("textarea", []))

    print("PASS: community-pack.yml is a valid Issue Form with all required fields")
    return 0


if __name__ == "__main__":
    sys.exit(main())
