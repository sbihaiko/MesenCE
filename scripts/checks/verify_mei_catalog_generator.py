#!/usr/bin/env python3
"""AC-2 (F6.3) — generate_community_pack_catalog.py writes an MEI v1.1
JSON catalog alongside the Markdown, using the new mep-meta parser.

Offline, no-`gh`, no-network structural checker, mirroring the pattern of
scripts/checks/verify_community_pack_catalog.py: this script never invokes
`generate_community_pack_catalog.py`'s `main()` (that needs a live `gh`
session with Project access this environment doesn't have) — it inspects
the generator's own source text and its dependency-free leaf modules
(mei_catalog_entry.py, community_pack_row.py) instead.

Checks:
  1. The generator writes docs/community-packs.json (a JSON_OUTPUT_PATH-
     shaped constant, and main() writing to it).
  2. It imports and uses mep_meta_parser.parse_mep_meta (ADR-0138 §27).
  3. It derives an MEI `kind` value (via mei_catalog_entry.kind_from_status
     or an equivalent "mep"/"hd-legacy" mapping, ADR-0138 §26).
  4. Its Markdown table header declares an "External assets" column and the
     six pre-existing columns (Link/Game/Console/Author/Category/Date)
     stay intact (AC-6's REQUIRED_COLUMNS, unchanged).

Usage: python3 scripts/checks/verify_mei_catalog_generator.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts/generate_community_pack_catalog.py"
LEAF = ROOT / "scripts/mei_catalog_entry.py"

EXISTING_COLUMNS = ["Link", "Game", "Console", "Author", "Category", "Date"]


def _read(path, failures):
    if not path.exists():
        failures.append(f"missing file: {path}")
        return ""
    return path.read_text(encoding="utf-8")


def check_writes_json_catalog(failures, text):
    if "community-packs.json" not in text:
        failures.append("generator does not reference docs/community-packs.json")
    if "JSON_OUTPUT_PATH" not in text:
        failures.append("generator has no JSON_OUTPUT_PATH-shaped output constant")
    if ".write_text(" not in text or "json.dumps(" not in text:
        failures.append("generator does not appear to write a JSON document (json.dumps + write_text)")


def check_uses_mep_meta_parser(failures, text):
    if "mep_meta_parser" not in text:
        failures.append("generator does not import mep_meta_parser")
    if "parse_mep_meta" not in text:
        failures.append("generator does not call parse_mep_meta")


def check_derives_kind(failures, script_text, leaf_text):
    if "kind" not in script_text and "kind" not in leaf_text:
        failures.append("neither the generator nor mei_catalog_entry.py mentions a 'kind' value")
        return
    if "hd-legacy" not in leaf_text and "hd-legacy" not in script_text:
        failures.append("no 'hd-legacy' kind derivation found (ADR-0138 §26)")
    if "mep" not in leaf_text and '"mep"' not in script_text:
        failures.append("no 'mep' kind branch found (ADR-0138 §26)")


def check_external_assets_column(failures, text):
    if "External assets" not in text:
        failures.append("Markdown table header does not declare an 'External assets' column")
    for col in EXISTING_COLUMNS:
        if col not in text:
            failures.append(f"generator no longer references pre-existing column {col!r}")


def main():
    failures = []
    script_text = _read(SCRIPT, failures)
    leaf_text = _read(LEAF, failures)
    if not script_text:
        print("FAIL: AC-2 (MEI catalog generator)")
        print(" - missing file, cannot run further checks")
        return 1
    check_writes_json_catalog(failures, script_text)
    check_uses_mep_meta_parser(failures, script_text)
    check_derives_kind(failures, script_text, leaf_text)
    check_external_assets_column(failures, script_text)
    if failures:
        print("FAIL: AC-2 (MEI catalog generator)")
        for item in failures:
            print(f" - {item}")
        return 1
    print("PASS: AC-2 (MEI catalog generator writes docs/community-packs.json, "
          "uses mep_meta_parser, derives kind, and the table gains External assets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
