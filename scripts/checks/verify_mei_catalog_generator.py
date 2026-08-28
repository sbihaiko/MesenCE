#!/usr/bin/env python3
"""AC-2 (F6.3) — generate_community_pack_catalog.py writes an MEI v1.1
JSON catalog alongside the Markdown, using the new mep-meta parser.

Offline, no-`gh`, no-network structural checker, mirroring the pattern of
scripts/checks/verify_community_pack_catalog.py: this script never invokes
`generate_community_pack_catalog.py`'s `main()` (that needs a live `gh`
session with Project access this environment doesn't have) — it inspects
the generator's own source text instead.

Checks:
  1. The generator writes docs/community-packs.json (a JSON_OUTPUT_PATH-
     shaped constant, and main() writing to it).
  2. It imports and uses mep_meta_parser.parse_mep_meta (ADR-0138 §27).
  3. It derives an MEI `kind` value (via kind_from_status or an equivalent
     "mep"/"hd-legacy" mapping, ADR-0138 §26).
  4. Its Markdown table header declares an "External assets" column and the
     six pre-existing columns (Link/Game/Console/Author/Category/Date)
     stay intact (AC-6's REQUIRED_COLUMNS, unchanged).
  5. Behavioral (imports the real modules, no mocks): a kind=="mep" entry
     built from mep-meta carrying `recipe.pack.version`/`pack.mep`
     round-trips through the real validate_mei (scripts/validate-specs.py)
     with zero failures; one built from mep-meta with no recipe at all is
     flagged non-conformant so the caller omits it, instead of the
     validate_mei-rejected entry a prior generator version produced.
  6. A lowercase, human-entered ROM SHA1 normalizes to 40-UPPERCASE-hex
     and an unparsable one is omitted rather than copied verbatim.

Usage: python3 scripts/checks/verify_mei_catalog_generator.py
"""
import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "scripts"
SCRIPT = SCRIPTS_DIR / "generate_community_pack_catalog.py"

EXISTING_COLUMNS = ["Link", "Game", "Console", "Author", "Category", "Date"]

sys.path.insert(0, str(SCRIPTS_DIR))
import generate_community_pack_catalog as gen  # noqa: E402


def _load_validate_specs():
    """Imports scripts/validate-specs.py by path (its hyphenated name
    isn't a valid module identifier for a plain `import`)."""
    spec = importlib.util.spec_from_file_location(
        "validate_specs", SCRIPTS_DIR / "validate-specs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATE_SPECS = _load_validate_specs()

FULL_RECIPE = {
    "recipe": 1,
    "sources": {"primary": {"url": "https://example.org/a.zip", "sha256": "a" * 64}},
    "ops": [{"op": "copy", "from": "primary:hires.txt", "to": "hires.txt"}],
    "pack": {"mep": "1.1.0", "name": "Synthetic", "version": "1.0.0",
              "license": "CC0-1.0", "targets": [{"system": "nes", "sha1": "A" * 40}],
              "sections": {"textures": {"path": ""}}},
}


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


def check_derives_kind(failures, script_text):
    if "kind" not in script_text:
        failures.append("generator does not mention a 'kind' value")
        return
    if "hd-legacy" not in script_text:
        failures.append("no 'hd-legacy' kind derivation found (ADR-0138 §26)")
    if '"mep"' not in script_text:
        failures.append("no 'mep' kind branch found (ADR-0138 §26)")


def check_external_assets_column(failures, text):
    if "External assets" not in text:
        failures.append("Markdown table header does not declare an 'External assets' column")
    for col in EXISTING_COLUMNS:
        if col not in text:
            failures.append(f"generator no longer references pre-existing column {col!r}")


def _validate_entry(entry):
    """Round-trips one packs[] entry through the real validate_mei (no
    mocks): writes it into a minimal MEI catalog temp file and returns
    whatever failures validate_mei records for it."""
    catalog = {"mei": "1.1.0", "name": "t", "maintainer": "t",
               "updated": "2026-01-01", "packs": [entry]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(catalog, handle)
        path = Path(handle.name)
    VALIDATE_SPECS._failures.clear()
    VALIDATE_SPECS.validate_mei(path)
    failures = list(VALIDATE_SPECS._failures)
    path.unlink()
    return failures


def _build_test_entry(issue_number, pack_hash, status, mep_meta, rom_sha1=None):
    entry, _ = gen.build_pack_entry(
        issue_number=issue_number, game="Synthetic", system="nes", license_="CC0-1.0",
        pack_url="https://example.org/pack.zip", pack_hash=pack_hash,
        rom_sha1=rom_sha1, status=status, mep_meta=mep_meta,
    )
    return entry


def check_mep_kind_with_recipe_conforms(failures, _text):
    entry = _build_test_entry(1, "b" * 64, gen.STATUS_MEP_COMPLETO,
                               {"recipe": copy.deepcopy(FULL_RECIPE)})
    if not gen.mei_entry_conforms(entry, "mep"):
        failures.append("mep-kind entry with a full recipe should conform (has version/mep)")
        return
    mei_failures = _validate_entry(entry)
    if mei_failures:
        failures.append(f"mep-kind entry with a full recipe failed validate_mei: {mei_failures}")


def check_mep_kind_without_recipe_flagged(failures, _text):
    entry = _build_test_entry(2, "c" * 64, gen.STATUS_MEP_COMPLETO, None)
    if gen.mei_entry_conforms(entry, "mep"):
        failures.append(
            "mep-kind entry with no mep-meta recipe should NOT conform -- it lacks "
            "version/mep and the real validate_mei rejects it (regression the "
            "caller must omit rather than pass through as a JSON entry)")


def check_rom_sha1_normalization(failures, _text):
    lower = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
    if gen.normalized_rom_sha1(lower) != lower.upper():
        failures.append("normalized_rom_sha1 did not uppercase a valid lowercase sha1")
    if gen.normalized_rom_sha1("not-a-sha1") is not None:
        failures.append("normalized_rom_sha1 should return None for a malformed value")
    entry = _build_test_entry(3, "d" * 64, gen.STATUS_HD_PARCIAL, None, rom_sha1=lower)
    if entry.get("rom", {}).get("sha1") != lower.upper():
        failures.append(f"build_pack_entry did not normalize rom.sha1: {entry.get('rom')}")
    mei_failures = _validate_entry(entry)
    if mei_failures:
        failures.append(f"hd-legacy entry with a normalized rom.sha1 failed validate_mei: {mei_failures}")


def main():
    failures = []
    script_text = _read(SCRIPT, failures)
    if not script_text:
        print("FAIL: AC-2 (MEI catalog generator)")
        print(" - missing file, cannot run further checks")
        return 1
    check_writes_json_catalog(failures, script_text)
    check_uses_mep_meta_parser(failures, script_text)
    check_derives_kind(failures, script_text)
    check_external_assets_column(failures, script_text)
    check_mep_kind_with_recipe_conforms(failures, script_text)
    check_mep_kind_without_recipe_flagged(failures, script_text)
    check_rom_sha1_normalization(failures, script_text)
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
