#!/usr/bin/env python3
"""Framework-free checks for scripts/mei_rules.py (F6.3b, ADR-0138 §28/§29).

Covers: the constants exposed by the leaf (SYSTEMS/MEI_KINDS/hash regexes/
SEMVER), required_mei_pack_fields' kind-conditional required-field list,
mei_entry_conforms' pass/fail behavior per kind, and resolve_kind's
mep-meta-first / Status-fallback / None-when-unmapped precedence (§29).

Usage: python3 scripts/test_mei_rules.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import mei_rules  # noqa: E402

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def check_constants_shape():
    if "nes" not in mei_rules.SYSTEMS or "gb" not in mei_rules.SYSTEMS:
        fail(f"SYSTEMS missing expected consoles: {mei_rules.SYSTEMS!r}")
        return
    if mei_rules.MEI_KINDS != {"mep", "hd-legacy"}:
        fail(f"MEI_KINDS unexpected: {mei_rules.MEI_KINDS!r}")
        return
    if not mei_rules.SEMVER.match("1.1.0") or mei_rules.SEMVER.match("1.1"):
        fail("SEMVER regex does not match exactly MAJOR.MINOR.PATCH")
        return
    if not mei_rules.SHA256_HEX.match("a" * 64) or mei_rules.SHA256_HEX.match("a" * 63):
        fail("SHA256_HEX regex does not require exactly 64 hex digits")
        return
    if not mei_rules.SHA1_UPPER.match("A" * 40) or mei_rules.SHA1_UPPER.match("a" * 40):
        fail("SHA1_UPPER regex should require UPPERCASE hex")
        return
    if not mei_rules.CRC32_UPPER.match("ABCD1234") or not mei_rules.MD5_UPPER.match("A" * 32):
        fail("CRC32_UPPER/MD5_UPPER regex shape is wrong")
        return
    ok("SYSTEMS/MEI_KINDS/SEMVER/hash regexes have the expected shape")


def check_required_fields_hd_legacy_omits_version_mep():
    fields = mei_rules.required_mei_pack_fields("hd-legacy")
    if "version" in fields or "mep" in fields:
        fail(f"hd-legacy required fields should omit version/mep: {fields!r}")
        return
    for base in ("name", "game", "system", "rom", "url", "sha256"):
        if base not in fields:
            fail(f"hd-legacy required fields missing base field {base!r}: {fields!r}")
            return
    ok("required_mei_pack_fields('hd-legacy') omits version/mep")


def check_required_fields_mep_and_none_include_version_mep():
    for kind in ("mep", None):
        fields = mei_rules.required_mei_pack_fields(kind)
        if "version" not in fields or "mep" not in fields:
            fail(f"required_mei_pack_fields({kind!r}) should require version/mep: {fields!r}")
            return
    ok("required_mei_pack_fields('mep'/None) require version/mep")


def _base_entry(**overrides):
    entry = {
        "name": "Pack", "game": "Game", "system": "nes",
        "rom": {"system": "nes"}, "url": "https://example.com/p.zip",
        "sha256": "a" * 64,
    }
    entry.update(overrides)
    return entry


def check_mei_entry_conforms_hd_legacy_without_version():
    entry = _base_entry()
    if not mei_rules.mei_entry_conforms(entry, "hd-legacy"):
        fail("hd-legacy entry without version/mep should conform")
        return
    ok("mei_entry_conforms('hd-legacy') accepts an entry without version/mep")


def check_mei_entry_conforms_mep_requires_version_and_mep():
    incomplete = _base_entry()
    if mei_rules.mei_entry_conforms(incomplete, "mep"):
        fail("mep entry missing version/mep should not conform")
        return
    complete = _base_entry(version="1.0.0", mep="1.1.0")
    if not mei_rules.mei_entry_conforms(complete, "mep"):
        fail("mep entry with version/mep should conform")
        return
    ok("mei_entry_conforms('mep') requires version/mep")


def check_mei_entry_conforms_accepts_empty_rom_dict():
    # MEI v1.1: rom.sha1 MAY be absent regardless of kind; validate_mei only
    # checks "rom" in p (presence), never its truthiness -- an entry whose
    # `rom` is `{}` (no ROM SHA1 available) must still conform.
    hd_legacy = _base_entry(rom={})
    if not mei_rules.mei_entry_conforms(hd_legacy, "hd-legacy"):
        fail("hd-legacy entry with an empty rom dict should still conform")
        return
    mep = _base_entry(rom={}, version="1.0.0", mep="1.1.0")
    if not mei_rules.mei_entry_conforms(mep, "mep"):
        fail("mep entry with an empty rom dict should still conform")
        return
    missing_rom = dict(_base_entry())
    del missing_rom["rom"]
    if mei_rules.mei_entry_conforms(missing_rom, "hd-legacy"):
        fail("an entry with no 'rom' key at all should not conform")
        return
    ok("mei_entry_conforms accepts an empty rom dict but requires the key to be present")


def check_mei_entry_conforms_rejects_unknown_kind():
    if mei_rules.mei_entry_conforms(_base_entry(version="1.0.0", mep="1.1.0"), "bogus"):
        fail("an unknown kind should never conform")
        return
    ok("mei_entry_conforms rejects an unknown kind")


def check_resolve_kind_prefers_mep_meta():
    kind = mei_rules.resolve_kind({"kind": "mep"}, "Aceito parcial (HD Mesen)")
    if kind != "mep":
        fail(f"resolve_kind should prefer a valid mep-meta kind, got {kind!r}")
        return
    ok("resolve_kind prefers a valid mep-meta kind over Status")


def check_resolve_kind_falls_back_to_status():
    for mep_meta in (None, {}, {"kind": "not-a-real-kind"}, "not-a-dict"):
        kind = mei_rules.resolve_kind(mep_meta, "Aceito parcial (HD Mesen)")
        if kind != "hd-legacy":
            fail(f"resolve_kind({mep_meta!r}, ...) should fall back to STATUS_TO_KIND, got {kind!r}")
            return
    ok("resolve_kind falls back to STATUS_TO_KIND[status] when mep-meta has no usable kind")


def check_resolve_kind_returns_none_when_unmapped():
    kind = mei_rules.resolve_kind(None, "Novo envio")
    if kind is not None:
        fail(f"resolve_kind should return None for an unmapped Status, got {kind!r}")
        return
    kind = mei_rules.resolve_kind({"kind": "invalid"}, "Novo envio")
    if kind is not None:
        fail(f"resolve_kind should never fall back to a kind-less non-None value, got {kind!r}")
        return
    ok("resolve_kind returns None (never kind-less) for an unmapped Status with no usable mep-meta kind")


def check_status_to_kind_matches_resolve_kind_fallback():
    for status, kind in mei_rules.STATUS_TO_KIND.items():
        if mei_rules.resolve_kind(None, status) != kind:
            fail(f"resolve_kind fallback diverges from STATUS_TO_KIND for status {status!r}")
            return
    ok("resolve_kind's Status fallback matches STATUS_TO_KIND for every mapped Status")


def main():
    check_constants_shape()
    check_required_fields_hd_legacy_omits_version_mep()
    check_required_fields_mep_and_none_include_version_mep()
    check_mei_entry_conforms_hd_legacy_without_version()
    check_mei_entry_conforms_mep_requires_version_and_mep()
    check_mei_entry_conforms_accepts_empty_rom_dict()
    check_mei_entry_conforms_rejects_unknown_kind()
    check_resolve_kind_prefers_mep_meta()
    check_resolve_kind_falls_back_to_status()
    check_resolve_kind_returns_none_when_unmapped()
    check_status_to_kind_matches_resolve_kind_fallback()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nAll mei_rules checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
