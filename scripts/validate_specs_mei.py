"""MEI v1.1 catalog validators (docs/specs/MEI-v1.md §2.2/§2.3), split out
of validate-specs.py to keep that file under the project's line-count
threshold (ADR-0138 §24 split convention). Imports its primitives from
the dependency-free scripts/spec_validate_common.py leaf; never imports
validate-specs.py itself back (that file is a script entry point, not an
importable module -- its filename is hyphenated).
"""
import json

from spec_validate_common import SPECS, SEMVER, SHA256_HEX, check, validate_rom_id

MEI_KINDS = {"mep", "hd-legacy"}

def validate_mei(path):
    """MEI v1.1 (docs/specs/MEI-v1.md §2.2/§2.3). `kind` (when present) is
    "mep" or "hd-legacy"; "hd-legacy" entries MAY omit `version`/`mep`
    (they predate MEP and have no pack.json to mirror). `rom.sha1` MAY be
    absent regardless of `kind` (§2.3). Each `deps[]` entry, when present,
    MUST carry `license` (§2.3), matching MEP-recipe-v1 §3.3's dep shape."""
    d = json.loads(path.read_text())
    for field in ("mei", "name", "packs"):
        check(field in d, f"{path.name}: required field missing: {field}")
    check(bool(SEMVER.match(d.get("mei", ""))), f"{path.name}: 'mei' is not semver")
    for i, p in enumerate(d.get("packs", [])):
        where = f"{path.name}: packs[{i}]"
        kind = p.get("kind")
        check(kind is None or kind in MEI_KINDS, f"{where}: invalid kind: {kind!r}")
        is_hd_legacy = kind == "hd-legacy"
        required = ["name", "game", "system", "rom", "license", "url", "sha256"]
        if not is_hd_legacy:
            required += ["version", "mep"]
        for field in required:
            check(field in p, f"{where}: required field missing: {field}")
        if "version" in p:
            check(bool(SEMVER.match(p.get("version", ""))), f"{where}: version is not semver")
        if "mep" in p:
            check(bool(SEMVER.match(p.get("mep", ""))), f"{where}: mep is not semver")
        check(p.get("url", "").startswith("https://"), f"{where}: url must be HTTPS")
        check(bool(SHA256_HEX.match(p.get("sha256", ""))), f"{where}: invalid sha256")
        rom = dict(p.get("rom", {}))
        rom.setdefault("system", p.get("system"))
        validate_rom_id(rom, f"{where}.rom", require_sha1=False)
        for j, dep in enumerate(p.get("deps", [])):
            check("license" in dep, f"{where}.deps[{j}]: required field missing: license")

def validate_mei_catalog():
    """ADR-0138 §§26-27: runs validate_mei()'s v1.1 rules over the golden
    and, when the repo has one, over the generated docs/community-packs.json
    catalog too. The committed catalog is skipped (not failed) when absent:
    this sandboxed environment has no gh access to regenerate it."""
    validate_mei(SPECS / "golden" / "mei" / "manifest.json")
    catalog_path = SPECS.parent / "community-packs.json"
    if catalog_path.exists():
        validate_mei(catalog_path)
