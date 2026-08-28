"""Dependency-free primitives shared by scripts/validate-specs.py and its
per-spec companion modules (ADR-0138 §24 split convention): the path
constant, the hash/semver regexes, and the check()/_failures accumulator.
Kept free of any spec-specific validation logic, so no companion module
(e.g. validate_specs_mei.py) ever needs to import validate-specs.py back
-- validate-specs.py is a script entry point (hyphenated filename), not
an importable module, and a back-import would double-execute its CLI
under a second module name.
"""
import re
from pathlib import Path

SPECS = Path(__file__).resolve().parent.parent / "docs" / "specs"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
SHA1_UPPER = re.compile(r"^[0-9A-F]{40}$")
CRC32_UPPER = re.compile(r"^[0-9A-F]{8}$")
MD5_UPPER = re.compile(r"^[0-9A-F]{32}$")
SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")
SYSTEMS = {"nes", "gb", "gbc", "sms", "gg", "sg1000", "coleco", "snes"}

_failures = []

def check(cond, msg):
    """Records `msg` as a failure when `cond` is false; never raises, so a
    single bad golden reports every violation instead of stopping at the
    first one."""
    if not cond:
        _failures.append(msg)

def validate_rom_id(entry, where, require_sha1=True):
    """Validates a {system, sha1?, crc32?, md5?} ROM identifier. `sha1` is
    required unless `require_sha1=False` and the field is simply absent
    (MEI v1.1 §2.3: `rom.sha1` MAY be absent)."""
    check(entry.get("system") in SYSTEMS, f"{where}: invalid system: {entry.get('system')}")
    if require_sha1 or "sha1" in entry:
        check(bool(SHA1_UPPER.match(entry.get("sha1", ""))),
              f"{where}: sha1 must be 40 UPPERCASE hex digits")
    if "crc32" in entry:
        check(bool(CRC32_UPPER.match(entry["crc32"])),
              f"{where}: crc32 must be 8 UPPERCASE hex digits")
    if "md5" in entry:
        check(bool(MD5_UPPER.match(entry["md5"])),
              f"{where}: md5 must be 32 UPPERCASE hex digits")
