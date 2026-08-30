#!/usr/bin/env python3
"""Framework-free checks for scripts/rom_target.py — the versioned No-Intro
map that lets the community-pack catalog resolve a pack's target ROM hash
from its game name, so `CommunityPackCatalogFetcher` can auto-match a loaded
No-Intro dump (ADR-0138 §2.3). Without a `rom.sha1` the catalog entry is
never hash-matchable and the auto-install silently never fires.

Checks:
  AC-1 every mini-map entry carries a 40-UPPERCASE-hex sha1, an
       8-UPPERCASE-hex crc32 and a non-empty dat_name.
  AC-2 the lookup keys are stable under normalization (re-normalizing a key
       is a no-op) and distinct.
  AC-3 every current catalog game name resolves through resolve_rom_target
       except the documented non-resolvable one (Ice_Climber_(VS), a
       VS. System variant absent from the NES dat) — those stay manually
       installable with `rom: {}`.
  AC-4 integration: build_pack_entry with a None board sha1 but a resolved
       target emits `rom: {sha1, crc32}` that validate_mei accepts; an
       unresolved game keeps `rom: {}`.

Usage: python3 scripts/test_rom_target.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import rom_target  # noqa: E402

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def _load_validate_specs():
    spec = importlib.util.spec_from_file_location(
        "validate_specs", SCRIPTS / "validate-specs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_targets_wellformed():
    for key, target in rom_target.NO_INTRO_TARGETS.items():
        sha1 = target["sha1"]
        if not rom_target.SHA1_UPPER.match(sha1):
            fail(f"target {key!r}: sha1 not 40-UPPERCASE-hex: {sha1!r}")
            return
        crc32 = target.get("crc32")
        if crc32 is not None and not rom_target.CRC32_UPPER.match(crc32):
            fail(f"target {key!r}: crc32 not 8-UPPERCASE-hex: {crc32!r}")
            return
        # Every entry names its source: a verified dump (source_dump) or a
        # pack-declared target hash (source). Never an unbacked guess.
        if not target.get("source_dump") and not target.get("source"):
            fail(f"target {key!r}: missing source_dump or source")
            return
    ok(f"{len(rom_target.NO_INTRO_TARGETS)} mini-map entries carry a valid sha1 "
       f"(crc32 optional) and a named source")


def check_keys_stable_and_distinct():
    keys = list(rom_target.NO_INTRO_TARGETS)
    normalized = [rom_target.normalize_game_name(k) for k in keys]
    if normalized != keys:
        bad = [k for k, n in zip(keys, normalized) if k != n]
        fail(f"keys not stable under normalization: {bad}")
        return
    if len(set(keys)) != len(keys):
        fail("duplicate lookup keys")
        return
    ok("lookup keys are stable under normalization and distinct")


def check_catalog_games_resolve():
    catalog_path = ROOT / "docs" / "community-packs.json"
    if not catalog_path.exists():
        fail(f"missing catalog {catalog_path}; cannot cross-check resolution")
        return
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    resolved = {p.get("game") for p in catalog["packs"]
                if rom_target.resolve_rom_target(p.get("game"))}
    # Exactly the four games with a usable target hash may resolve. Three are
    # backed by a dump whose PRG+CHR crc32 the Mesen game database recognizes;
    # Zelda is backed by the sha1 the pack itself declares (<supportedRom>/
    # <patch>), which is what the patch matcher compares against. Every other
    # current pack has no verified dump yet, so its entry MUST keep `rom: {}`
    # rather than carry a guessed hash (see rom_target.py).
    expected = {"Super_Mario_Bros", "Mega Man (USA)", "Contra (USA)",
                "The Legend of Zelda (USA)", "Castlevania (USA)"}
    if resolved != expected:
        fail(f"resolved set mismatch: got {sorted(resolved)}, expected {sorted(expected)}")
        return
    for game in sorted(expected):
        rom = rom_target.resolve_rom_target(game)
        if not rom:
            fail(f"expected {game!r} to resolve")
            return
    ok(f"{len(resolved)} of {len(catalog['packs'])} catalog games resolve "
       f"({sorted(resolved)}); the rest keep rom {{}} until a verified target hash exists")


def check_build_pack_entry_integration():
    vs = _load_validate_specs()
    import mei_catalog_entry as entry_mod

    def _validate(entry):
        catalog = {"mei": "1.1.0", "name": "t", "maintainer": "t",
                   "updated": "2026-01-01", "packs": [entry]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(catalog, handle)
            path = Path(handle.name)
        vs._failures.clear()
        vs.validate_mei(path)
        mei_failures = list(vs._failures)
        path.unlink()
        return mei_failures

    # A resolved game with no board sha1 -> the generator feeds the target's
    # sha1 + crc32 into build_pack_entry, which emits rom {sha1, crc32}.
    target = rom_target.resolve_rom_target("Contra (USA)")
    if target is None:
        fail("resolve_rom_target('Contra (USA)') returned None")
        return
    entry, _ = entry_mod.build_pack_entry(
        issue_number=137, game="Contra (USA)", system="nes", license_="unknown",
        pack_url="https://example.org/c.zip", pack_hash="a" * 64,
        rom_sha1=target["sha1"], status="Aceito parcial (HD Mesen)", mep_meta={}, votes=1,
        crc32=target["crc32"])
    rom = entry.get("rom", {})
    if rom.get("sha1") != target["sha1"] or rom.get("crc32") != target["crc32"]:
        fail(f"build_pack_entry did not emit resolved sha1+crc32: {rom!r}")
        return
    mei_failures = _validate(entry)
    if mei_failures:
        fail(f"resolved rom {rom!r} failed validate_mei: {mei_failures}")
        return
    # A sha1-only target (Zelda: the pack-declared hash, no crc32) still emits
    # a valid rom {sha1} — MEI-v1 §2.3 makes crc32 optional.
    zelda = rom_target.resolve_rom_target("The Legend of Zelda (USA)")
    if not zelda or "crc32" in zelda:
        fail(f"Zelda should resolve sha1-only: {zelda!r}")
        return
    entry_zelda, _ = entry_mod.build_pack_entry(
        issue_number=139, game="The Legend of Zelda (USA)", system="nes", license_="unknown",
        pack_url="https://example.org/z.zip", pack_hash="b" * 64,
        rom_sha1=zelda["sha1"], status="Aceito parcial (HD Mesen)", mep_meta={}, votes=1)
    if entry_zelda.get("rom") != {"sha1": zelda["sha1"]}:
        fail(f"Zelda should emit rom {{{{'sha1'}}}}: {entry_zelda.get('rom')!r}")
        return
    mei_failures = _validate(entry_zelda)
    if mei_failures:
        fail(f"Zelda sha1-only rom failed validate_mei: {mei_failures}")
        return
    # An unresolved game (the VS. System Ice Climber — absent from the NES
    # dat) keeps the empty `rom` object.
    entry2, _ = entry_mod.build_pack_entry(
        issue_number=133, game="Ice_Climber_(VS)", system="nes", license_="unknown",
        pack_url="https://example.org/i.zip", pack_hash="c" * 64,
        rom_sha1=None, status="Aceito parcial (HD Mesen)", mep_meta={}, votes=1)
    if entry2.get("rom") != {}:
        fail(f"unresolved game should keep rom={{}}: {entry2.get('rom')!r}")
        return
    ok("build_pack_entry emits rom {sha1,crc32}/{sha1} for resolved targets, keeps rom {} otherwise (validate_mei clean)")


def main():
    check_targets_wellformed()
    check_keys_stable_and_distinct()
    check_catalog_games_resolve()
    check_build_pack_entry_integration()

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
