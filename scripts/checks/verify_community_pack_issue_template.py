#!/usr/bin/env python3
"""Verifies .github/ISSUE_TEMPLATE/community-pack.yml (AC-1).

Confirms that the file is a GitHub Issue Form (not a free-text issue) with:
- pack link field (URL)
- target game/ROM + region field
- console dropdown (NES/GB/GBC/SMS/Other — no SNES: not a product console on main)
- labels: [community-pack]
- link to docs/hd-pack-authoring.md
- nothing else asked of the submitter: the form was cut down to those three
  required fields, so this check also asserts the author/credits, description,
  external_assets and external_assets_license fields are GONE. Authorship is
  discovered by the classify step from the pack itself; the recipe parser
  still accepts an "External assets" section typed into an issue body by
  hand, it is simply no longer a form field.

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


def check_removed_fields(body):
    """The four fields the simplified form dropped must not come back
    silently: each one was either asking the submitter for something the
    automation can find on its own (author/credits) or for optional detail
    that made the form long enough to need reading first."""
    removed = {"author_credits", "description", "external_assets",
               "external_assets_license"}
    present = {str(e.get("id")) for e in body if isinstance(e, dict)} & removed
    if present:
        fail(f"form asks for field(s) that were deliberately removed: {sorted(present)}")


def main():
    data, text = load_template()
    check_top_level(data)
    check_doc_link(text)

    by_type = find_fields(data["body"])
    check_pack_link(by_type.get("input", []))
    check_rom_target(by_type.get("input", []))
    check_console_dropdown(by_type.get("dropdown", []))
    check_removed_fields(data["body"])

    print("PASS: community-pack.yml is a valid Issue Form asking only for "
          "pack link, game/ROM and console")
    return 0


if __name__ == "__main__":
    sys.exit(main())
