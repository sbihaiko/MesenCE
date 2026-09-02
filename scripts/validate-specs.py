#!/usr/bin/env python3
"""Validates the golden files under docs/specs/ against the normative rules
of the ESP v1, MEP v1 (incl. the v1.5 border section), MEI v1.3, MEP-recipe v1 specs and the hires-gbsms draft,
and enforces the wire format of shared cross-language test fixtures
(path-cases.txt, ADR-0124); also lints every MEP golden root via mep_lint.py (ADR-0136). Exits non-zero on the first violation. Run from the repo root:
python3 scripts/validate-specs.py
"""
import json, re, struct, subprocess, sys
from pathlib import Path

from mei_rules import (
    CRC32_UPPER,
    MD5_UPPER,
    MEI_KINDS,
    SEMVER,
    SHA1_UPPER,
    SHA256_HEX,
    SYSTEMS,
    mei_identity_field_errors,
    required_mei_pack_fields,
)

SPECS = Path(__file__).resolve().parent.parent / "docs" / "specs"

ESP_PRESETS = {"Synthwave", "ChipDeluxe", "OrchestralLite", "Dry", "Studio"}
ESP_SUFFIXES = {"", ".Gb", ".Sms"}
ESP_DOUBLE_FIELDS = {
    "LeadDetune", "HarmDetune", "FixedWidth", "LeadOctaveUpMix", "LeadLpHz", "HarmLpHz", "LeadDrive", "BassSine",
    "BassSaw", "BassSub", "BassLpHz", "BassDrive", "DrumBodyLoHz", "DrumBodyHiHz", "DrumTopHz", "DrumBodyGain",
    "ThumpGain", "ThumpDecayS", "ThumpFreqHz", "AttackMs", "ReleaseMs", "EchoDelayS", "EchoGainL", "EchoGainR",
    "ReverbWet", "LeadGain", "HarmGain", "BassGain", "DrumGain", "CompThreshold", "CompRatio", "CompAttackMs",
    "CompReleaseMs", "CompMakeup",
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
            in_known_section = any(name == p + s for p in ESP_PRESETS for s in ESP_SUFFIXES)
            check(in_known_section or "." in name, f"{path.name}:{n}: section '{name}' is not '<Preset><Suffix>'")
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
            check(value in ("true", "false"), f"{path.name}:{n}: '{field}' must be true/false: {value}")
        # unknown field: allowed and ignored per spec (§3.5)
    check(known_field_count > 0, f"{path.name}: no ESP field recognized")

def validate_rom_id(entry, where, require_sha1=True):
    # `sha1` required unless require_sha1=False and simply absent (MEI v1.1 §2.3).
    check(entry.get("system") in SYSTEMS, f"{where}: invalid system: {entry.get('system')}")
    if require_sha1 or "sha1" in entry:
        check(bool(SHA1_UPPER.match(entry.get("sha1", ""))), f"{where}: sha1 must be 40 UPPERCASE hex digits")
    if "crc32" in entry:
        check(bool(CRC32_UPPER.match(entry["crc32"])), f"{where}: crc32 must be 8 UPPERCASE hex digits")
    if "md5" in entry:
        check(bool(MD5_UPPER.match(entry["md5"])), f"{where}: md5 must be 32 UPPERCASE hex digits")

def safe_relative_path(p):
    return not p.startswith("/") and ".." not in p.split("/")

def validate_mep(path):
    d = json.loads(path.read_text())
    for field in ("mep", "name", "version", "targets", "sections"):
        check(field in d, f"{path.name}: required field missing: {field}")
    # MEP-v1 §3.1: `license` is optional (SHOULD) since v1.1; when present it is a non-empty string.
    check("license" not in d or (isinstance(d["license"], str) and d["license"]), f"{path.name}: license must be a non-empty string when present")
    check(bool(SEMVER.match(d.get("mep", ""))), f"{path.name}: 'mep' is not semver")
    check(bool(SEMVER.match(d.get("version", ""))), f"{path.name}: 'version' is not semver")
    targets = d.get("targets", [])
    check(len(targets) >= 1, f"{path.name}: targets is empty")
    for i, t in enumerate(targets):
        validate_rom_id(t, f"{path.name}: targets[{i}]")
    sections = d.get("sections", {})
    check(len(sections) >= 1, f"{path.name}: sections is empty")
    for name, sec in sections.items():
        check(name in ("textures", "audio", "synth", "border"), f"{path.name}: unknown section '{name}' (ok if a future version)")
        check("path" in sec and safe_relative_path(sec["path"]), f"{path.name}: sections.{name}.path missing or unsafe")

def png_size(path):
    """(width, height) from the IHDR chunk of a PNG, or None when the file is not a PNG."""
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])

def validate_mep_border(root):
    """MEP-v1 §5.4 (v1.5, ADR-0149): the golden pack declares a `border` section whose folder holds a
    decodable `border.png` and a `border.json` with integer `width`/`height` > 0 matching the PNG and a
    `viewport` object that lies within the canvas."""
    pack = json.loads((root / "pack.json").read_text())
    section = pack.get("sections", {}).get("border")
    check(isinstance(section, dict) and "path" in section, f"{root.name}/pack.json: sections.border missing (MEP-v1 §5.4)")
    if not isinstance(section, dict):
        return
    folder = root / section.get("path", "").strip("/") if section.get("path", "").strip("/") else root
    png = folder / "border.png"
    check(png.is_file(), f"{root.name}: {png.relative_to(root)} does not exist")
    size = png_size(png) if png.is_file() else None
    check(size is not None and size[0] > 0 and size[1] > 0, f"{root.name}: {png.relative_to(root)} is not a decodable PNG")
    meta_path = folder / "border.json"
    check(meta_path.is_file(), f"{root.name}: {meta_path.relative_to(root)} does not exist")
    if not meta_path.is_file():
        return
    try:
        meta = json.loads(meta_path.read_text())
    except json.JSONDecodeError as exc:
        check(False, f"{root.name}: border.json invalid JSON: {exc}")
        return
    check(isinstance(meta, dict), f"{root.name}: border.json root must be an object")
    if not isinstance(meta, dict):
        return
    w, h = meta.get("width"), meta.get("height")
    def positive_int(v):
        return isinstance(v, int) and not isinstance(v, bool) and v > 0
    check(positive_int(w) and positive_int(h), f"{root.name}: border.json width/height must be integers > 0")
    if size is not None and positive_int(w) and positive_int(h):
        check((w, h) == tuple(size), f"{root.name}: border.json width/height {w}x{h} differ from border.png {size[0]}x{size[1]}")
    vp = meta.get("viewport")
    check(isinstance(vp, dict), f"{root.name}: border.json 'viewport' must be an object")
    if isinstance(vp, dict) and positive_int(w) and positive_int(h):
        x, y, vw, vh = (vp.get(k) for k in ("x", "y", "width", "height"))
        check(all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y)), f"{root.name}: viewport.x/y must be integers")
        check(positive_int(vw) and positive_int(vh), f"{root.name}: viewport.width/height must be integers > 0")
        if all(isinstance(v, int) for v in (x, y, vw, vh)):
            check(0 <= x and 0 <= y and x + vw <= w and y + vh <= h, f"{root.name}: viewport {x},{y} {vw}x{vh} exceeds the {w}x{h} canvas")
    check(meta.get("scale_mode", "fit") in ("fit", "stretch"), f"{root.name}: border.json scale_mode must be 'fit' or 'stretch'")
    check(isinstance(meta.get("underlay", False), bool), f"{root.name}: border.json underlay must be a boolean")

def lint_golden_packs():
    # ADR-0136 tripwire: previously nothing ran mep_lint.py over the goldens.
    mep_lint = str(Path(__file__).resolve().parent / "mep_lint.py")
    for root in (SPECS / "golden" / "mep", SPECS / "golden" / "mep-nes"):
        result = subprocess.run([sys.executable, mep_lint, str(root)], capture_output=True, text=True)
        check(result.returncode == 0, f"mep_lint.py exited {result.returncode} on {root}:\n{result.stdout}{result.stderr}")

def validate_mei(path):
    # MEI v1.1 §2.2/§2.3: "hd-legacy" `kind` needs no `version`/`mep`; `rom.sha1` MAY be absent regardless of `kind`; `license` (entry and each `deps[]` item) is SHOULD — a non-empty string when present.
    d = json.loads(path.read_text())
    for field in ("mei", "name", "packs"):
        check(field in d, f"{path.name}: required field missing: {field}")
    check(bool(SEMVER.match(d.get("mei", ""))), f"{path.name}: 'mei' is not semver")
    for i, p in enumerate(d.get("packs", [])):
        where = f"{path.name}: packs[{i}]"
        kind = p.get("kind")
        check(kind is None or kind in MEI_KINDS, f"{where}: invalid kind: {kind!r}")
        for field in required_mei_pack_fields(kind):
            check(field in p, f"{where}: required field missing: {field}")
        check("version" not in p or bool(SEMVER.match(p["version"])), f"{where}: version is not semver")
        check("mep" not in p or bool(SEMVER.match(p["mep"])), f"{where}: mep is not semver")
        check(p.get("url", "").startswith("https://"), f"{where}: url must be HTTPS")
        check(bool(SHA256_HEX.match(p.get("sha256", ""))), f"{where}: invalid sha256")
        rom = dict(p.get("rom", {}))
        rom.setdefault("system", p.get("system"))
        validate_rom_id(rom, f"{where}.rom", require_sha1=False)
        # MEI v1.2 §2.4: `rom.sha1s` is an additive list of 40-UPPERCASE-hex alternates, never repeating `rom.sha1`.
        if "sha1s" in rom:
            sha1s = rom["sha1s"]
            check(isinstance(sha1s, list) and len(sha1s) > 0, f"{where}.rom: sha1s must be a non-empty list")
            for k, alt in enumerate(sha1s if isinstance(sha1s, list) else []):
                check(isinstance(alt, str) and bool(SHA1_UPPER.match(alt)), f"{where}.rom.sha1s[{k}]: must be 40 UPPERCASE hex digits")
                check(alt != rom.get("sha1"), f"{where}.rom.sha1s[{k}]: repeats rom.sha1")
            check(len(set(sha1s)) == len(sha1s) if isinstance(sha1s, list) else True, f"{where}.rom: sha1s has duplicates")
        check("license" not in p or (isinstance(p["license"], str) and p["license"]), f"{where}: license must be a non-empty string when present")
        # MEI v1.3 §2.5: additive `pack_id` (lowercase slug / owner/repo[:game] / issue-N), `content_id` (64 lowercase hex, ADR-0139) and `votes` (int >= 0) — never empty, never the wrong type.
        for msg in mei_identity_field_errors(p):
            check(False, f"{where}: {msg}")
        for j, dep in enumerate(p.get("deps", [])):
            check("license" not in dep or (isinstance(dep["license"], str) and dep["license"]), f"{where}.deps[{j}]: license must be a non-empty string when present")

def validate_mei_catalog():
    # ADR-0138 §§26-27: also validates docs/community-packs.json when present (a generated artifact; skipped, not failed, when this checkout has none).
    validate_mei(SPECS / "golden" / "mei" / "manifest.json")
    catalog_path = SPECS.parent / "community-packs.json"
    if catalog_path.exists():
        validate_mei(catalog_path)

def validate_hires_draft(path):
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    check(lines and lines[0].startswith("<ver>"), f"{path.name}: first line must be <ver>")
    ver = int(lines[0][5:])
    check(ver >= 200, f"{path.name}: GB/SMS extension requires <ver> >= 200 (draft §2)")
    tags = {l[:l.index(">") + 1] for l in lines if l.startswith("<")}
    check("<system>" in tags, f"{path.name}: <system> is required at <ver> >= 200")
    system_line = next(l for l in lines if l.startswith("<system>"))
    check(system_line[8:] in ("gb", "gbc", "sms", "gg", "sg1000", "coleco"), f"{path.name}: invalid <system>: {system_line[8:]}")

PATH_CASE_LINE = re.compile(r"^[^\t]+\t(ok|bad)$")

def validate_path_cases(path):
    """Format-only guard: every non-blank, non-'#' line of the zip-slip
    fixture must be exactly one TAB-separated <path><TAB>ok|bad case. This
    does not interpret paths semantically (see ADR-0124) -- that is owned
    by the fixture's two real consumers, UI.Tests/Mep/MepZipValidatorTests.cs
    and scripts/core_unit_tests.cpp."""
    # Skip rules are byte-identical to the C++ reader in scripts/core_unit_tests.cpp (empty line, or '#' in column 0):
    # an indented comment would pass a looser guard and then fail the harness.
    case_count = 0
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if line == "" or line[0] == "#":
            continue
        m = PATH_CASE_LINE.match(line)
        check(bool(m), f"{path.name}:{n}: expected '<path><TAB>ok|bad', got: {line!r}")
        if m:
            # The C# reader Trim()s the line and the C++ one does not, so surrounding whitespace would feed two
            # different strings to the two suites from one shared case -- reject it here.
            path_col = line[:line.index("\t")]
            check(path_col == path_col.strip(), f"{path.name}:{n}: path column has leading/trailing whitespace: {line!r}")
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
    check(any(op.get("op") == "rewrite-paths" for op in ops), f"{path.name}: golden must exercise rewrite-paths")

def main():
    validate_esp(SPECS / "golden" / "esp" / "EnhancedAudioPresets.cfg")
    validate_mep(SPECS / "golden" / "mep" / "pack.json")
    validate_mep(SPECS / "golden" / "mep-nes" / "pack.json")
    validate_mep_border(SPECS / "golden" / "mep")
    validate_mei_catalog()
    validate_hires_draft(SPECS / "golden" / "hires-gbsms" / "hires.txt")
    validate_path_cases(SPECS / "golden" / "mep" / "path-cases.txt")
    validate_recipe(SPECS / "golden" / "mep-recipe" / "recipe.json")
    lint_golden_packs()
    if _failures:
        for f in _failures:
            print(f"FAILURE: {f}", file=sys.stderr)
        sys.exit(1)
    print("validate-specs: all golden files conform (ESP, MEP, MEI v1.3, MEP-recipe, hires-gbsms draft, path-cases format); "
          "mep-nes/pack.json structurally validated; mep border section (MEP v1.5 §5.4: border.png + border.json viewport) validated; "
          "mep + mep-nes lint-checked; MEI catalog validated (golden always, docs/community-packs.json when present)")

if __name__ == "__main__":
    main()
