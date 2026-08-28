#!/usr/bin/env python3
"""Validates the golden files under docs/specs/ against the normative rules
of the ESP v1, MEP v1, MEI v1, MEP-recipe v1 specs and the hires-gbsms draft,
and enforces the wire format of shared cross-language test fixtures
(path-cases.txt, see ADR-0124). Exits with a non-zero code on the first violation. Run from the repo root:
python3 scripts/validate-specs.py
"""
import json
import re
import sys
from pathlib import Path

SPECS = Path(__file__).resolve().parent.parent / "docs" / "specs"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
SHA1_UPPER = re.compile(r"^[0-9A-F]{40}$")
CRC32_UPPER = re.compile(r"^[0-9A-F]{8}$")
MD5_UPPER = re.compile(r"^[0-9A-F]{32}$")
SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")
SYSTEMS = {"nes", "gb", "gbc", "sms", "gg", "sg1000", "coleco", "snes"}

ESP_PRESETS = {"Synthwave", "ChipDeluxe", "OrchestralLite", "Dry", "Studio"}
ESP_SUFFIXES = {"", ".Gb", ".Sms"}
ESP_DOUBLE_FIELDS = {
    "LeadDetune", "HarmDetune", "FixedWidth", "LeadOctaveUpMix", "LeadLpHz",
    "HarmLpHz", "LeadDrive", "BassSine", "BassSaw", "BassSub", "BassLpHz",
    "BassDrive", "DrumBodyLoHz", "DrumBodyHiHz", "DrumTopHz", "DrumBodyGain",
    "ThumpGain", "ThumpDecayS", "ThumpFreqHz", "AttackMs", "ReleaseMs",
    "EchoDelayS", "EchoGainL", "EchoGainR", "ReverbWet", "LeadGain",
    "HarmGain", "BassGain", "DrumGain", "CompThreshold", "CompRatio",
    "CompAttackMs", "CompReleaseMs", "CompMakeup",
}
ESP_BOOL_FIELDS = {"FollowDuty", "LeadAlwaysSaw"}

_failures = []

def check(cond, msg):
    if not cond:
        _failures.append(msg)

def validate_esp(path):
    in_known_section = False
    known_field_count = 0
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1]
            in_known_section = any(
                name == p + s for p in ESP_PRESETS for s in ESP_SUFFIXES)
            check(in_known_section or "." in name,
                  f"{path.name}:{n}: section '{name}' is not '<Preset><Suffix>'")
            continue
        check("=" in line, f"{path.name}:{n}: line is neither a field nor a section")
        if "=" not in line or not in_known_section:
            continue
        field, value = (part.strip() for part in line.split("=", 1))
        if field in ESP_DOUBLE_FIELDS:
            known_field_count += 1
            try:
                float(value)
            except ValueError:
                check(False, f"{path.name}:{n}: '{field}' not numeric: {value}")
        elif field in ESP_BOOL_FIELDS:
            known_field_count += 1
            check(value in ("true", "false"),
                  f"{path.name}:{n}: '{field}' must be true/false: {value}")
        # unknown field: allowed and ignored per spec (§3.5)
    check(known_field_count > 0, f"{path.name}: no ESP field recognized")

def validate_rom_id(entry, where):
    check(entry.get("system") in SYSTEMS, f"{where}: invalid system: {entry.get('system')}")
    check(bool(SHA1_UPPER.match(entry.get("sha1", ""))),
          f"{where}: sha1 must be 40 UPPERCASE hex digits")
    if "crc32" in entry:
        check(bool(CRC32_UPPER.match(entry["crc32"])),
              f"{where}: crc32 must be 8 UPPERCASE hex digits")
    if "md5" in entry:
        check(bool(MD5_UPPER.match(entry["md5"])),
              f"{where}: md5 must be 32 UPPERCASE hex digits")

def safe_relative_path(p):
    return not p.startswith("/") and ".." not in p.split("/")

def validate_mep(path):
    d = json.loads(path.read_text())
    for field in ("mep", "name", "version", "license", "targets", "sections"):
        check(field in d, f"{path.name}: required field missing: {field}")
    check(bool(SEMVER.match(d.get("mep", ""))), f"{path.name}: 'mep' is not semver")
    check(bool(SEMVER.match(d.get("version", ""))), f"{path.name}: 'version' is not semver")
    targets = d.get("targets", [])
    check(len(targets) >= 1, f"{path.name}: targets is empty")
    for i, t in enumerate(targets):
        validate_rom_id(t, f"{path.name}: targets[{i}]")
    sections = d.get("sections", {})
    check(len(sections) >= 1, f"{path.name}: sections is empty")
    for name, sec in sections.items():
        check(name in ("textures", "audio", "synth"),
              f"{path.name}: unknown section '{name}' (ok if a future version)")
        check("path" in sec and safe_relative_path(sec["path"]),
              f"{path.name}: sections.{name}.path missing or unsafe")

def validate_mei(path):
    d = json.loads(path.read_text())
    for field in ("mei", "name", "packs"):
        check(field in d, f"{path.name}: required field missing: {field}")
    check(bool(SEMVER.match(d.get("mei", ""))), f"{path.name}: 'mei' is not semver")
    for i, p in enumerate(d.get("packs", [])):
        where = f"{path.name}: packs[{i}]"
        for field in ("name", "version", "game", "system", "rom", "mep",
                      "license", "url", "sha256"):
            check(field in p, f"{where}: required field missing: {field}")
        check(bool(SEMVER.match(p.get("version", ""))), f"{where}: version is not semver")
        check(bool(SEMVER.match(p.get("mep", ""))), f"{where}: mep is not semver")
        check(p.get("url", "").startswith("https://"), f"{where}: url must be HTTPS")
        check(bool(SHA256_HEX.match(p.get("sha256", ""))), f"{where}: invalid sha256")
        rom = dict(p.get("rom", {}))
        rom.setdefault("system", p.get("system"))
        validate_rom_id(rom, f"{where}.rom")

def validate_hires_draft(path):
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    check(lines and lines[0].startswith("<ver>"), f"{path.name}: first line must be <ver>")
    ver = int(lines[0][5:])
    check(ver >= 200, f"{path.name}: GB/SMS extension requires <ver> >= 200 (draft §2)")
    tags = {l[:l.index(">") + 1] for l in lines if l.startswith("<")}
    check("<system>" in tags, f"{path.name}: <system> is required at <ver> >= 200")
    system_line = next(l for l in lines if l.startswith("<system>"))
    check(system_line[8:] in ("gb", "gbc", "sms", "gg", "sg1000", "coleco"),
          f"{path.name}: invalid <system>: {system_line[8:]}")

PATH_CASE_LINE = re.compile(r"^[^\t]+\t(ok|bad)$")

def validate_path_cases(path):
    """Format-only guard: every non-blank, non-'#' line of the zip-slip
    fixture must be exactly one TAB-separated <path><TAB>ok|bad case. This
    does not interpret paths semantically (see ADR-0124) -- that is owned
    by the fixture's two real consumers, UI.Tests/Mep/MepZipValidatorTests.cs
    and scripts/core_unit_tests.cpp."""
    # Skip rules are byte-identical to the C++ reader in
    # scripts/core_unit_tests.cpp (empty line, or '#' in column 0): an
    # indented comment would pass a looser guard and then fail the harness.
    case_count = 0
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if line == "" or line[0] == "#":
            continue
        m = PATH_CASE_LINE.match(line)
        check(bool(m),
              f"{path.name}:{n}: expected '<path><TAB>ok|bad', got: {line!r}")
        if m:
            # The C# reader Trim()s the line and the C++ one does not, so
            # surrounding whitespace would feed two different strings to the
            # two suites from one shared case -- reject it here.
            path_col = line[:line.index("\t")]
            check(path_col == path_col.strip(),
                  f"{path.name}:{n}: path column has leading/trailing whitespace: {line!r}")
            case_count += 1
    check(case_count > 0, f"{path.name}: no path case recognized")

def validate_recipe(path):
    """MEP-recipe-v1 golden: same rules as scripts/mep_recipe.py validate."""
    import mep_recipe

    try:
        recipe = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        check(False, f"{path.name}: invalid JSON: {exc}")
        return
    for err in mep_recipe.validate_recipe(recipe):
        check(False, f"{path.name}: {err}")
    check(recipe.get("recipe") == 1, f"{path.name}: 'recipe' must be 1")
    ops = recipe.get("ops") or []
    check(any(op.get("op") == "copy" for op in ops), f"{path.name}: golden must exercise copy")
    check(any(op.get("op") == "glob" for op in ops), f"{path.name}: golden must exercise glob")
    check(any(op.get("op") == "rewrite-paths" for op in ops),
          f"{path.name}: golden must exercise rewrite-paths")


def main():
    validate_esp(SPECS / "golden" / "esp" / "EnhancedAudioPresets.cfg")
    validate_mep(SPECS / "golden" / "mep" / "pack.json")
    validate_mei(SPECS / "golden" / "mei" / "manifest.json")
    validate_hires_draft(SPECS / "golden" / "hires-gbsms" / "hires.txt")
    validate_path_cases(SPECS / "golden" / "mep" / "path-cases.txt")
    validate_recipe(SPECS / "golden" / "mep-recipe" / "recipe.json")
    if _failures:
        for f in _failures:
            print(f"FAILURE: {f}", file=sys.stderr)
        sys.exit(1)
    print("validate-specs: all golden files conform "
          "(ESP, MEP, MEI, MEP-recipe, hires-gbsms draft, path-cases format)")

if __name__ == "__main__":
    main()
