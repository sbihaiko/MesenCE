#!/usr/bin/env python3
"""Validates the golden files under docs/specs/ against the normative rules
of the ESP v1, MEP v1, MEI v1 specs and the hires-gbsms draft. Exits with a
non-zero code on the first violation. Run from the repo root:
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

def main():
    validate_esp(SPECS / "golden" / "esp" / "EnhancedAudioPresets.cfg")
    validate_mep(SPECS / "golden" / "mep" / "pack.json")
    validate_mei(SPECS / "golden" / "mei" / "manifest.json")
    validate_hires_draft(SPECS / "golden" / "hires-gbsms" / "hires.txt")
    if _failures:
        for f in _failures:
            print(f"FAILURE: {f}", file=sys.stderr)
        sys.exit(1)
    print("validate-specs: all golden files conform (ESP, MEP, MEI, hires-gbsms draft)")

if __name__ == "__main__":
    main()
