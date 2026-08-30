#!/usr/bin/env python3
"""From-zero community HD pack install + headless load verification (ADR-0138
SS50 client path; MEI-v1 §2.3 `kind: "hd-legacy"`).

Drives the same rules the client encodes (CommunityPackCatalogMatcher,
LegacyHdPackInstall, CommunityPackDrive - all unit-tested in UI.Tests) against
REAL ROMs and REAL pack zips, always starting from a zeroed state, and proves
the actual C++ loader picks the installed pack up headlessly:

  1. compute each ROM's No-Intro sha1 (Python mirror of
     MepPackManager::ComputeNoIntroSha1, ADR-0044);
  2. match against the live catalog (docs/community-packs.json) - exact sha1,
     an entry with no `rom.sha1` is never hash-matched;
  3. for matched ROMs, install from zero: wipe the scratch mesen-home
     (HdPacks/, EnhancementPacks/) and the catalog cache, download the
     artifact (scripts/fetch_pack.py - the allow-listed, sha256-capped,
     google-drive-two-step downloader the client mirrors), verify sha256
     against the catalog entry, extract into mesen-home/HdPacks/<romName>/
     using the same pack-root discovery + nested-zip unwrap as the client;
  4. boot the real ROM via scripts/headless_record (the C++ core, no GUI)
     and assert the loader log proves the HD pack loaded.

The report table doubles as the coverage diagnostic: a ROM with no catalog
match is "no match: <reason>" (a different dump of a catalogued game, or no
entry carries its hash at all) - that is correct client behavior, not a
failure. The sha1 mirror is cross-validated against scripts/rom_target.py on
the very same files when their names match, so a green coverage line also
proves the mirror reproduces the hashes the catalog was built from.

Exit 0 when every matched ROM installed and loaded headlessly; 1 otherwise
(or when a ROM the catalog targets turns out to be a non-matching dump while
its game is catalogued - see --strict).

Usage:
  python3 scripts/verify_community_install_from_zero.py <roms-dir>
      [--catalog FILE]        catalog JSON (default docs/community-packs.json)
      [--pack FILE]           force one pack zip for the matched ROM (else
                              --pack-dir, else download via fetch_pack.py)
      [--pack-dir DIR]        prefer a local zip whose basename equals the
                              catalog entry's URL basename over downloading
      [--work DIR]            scratch dir (default .cache/verify-from-zero)
      [--coverage-only]       report matches/no-matches without installing
      [--rom PATH]            restrict to one ROM file (by name or path)
      [--verify-pack-only ZIP] extract a pack zip into a scratch home using
                              the client's root discovery and run mep_lint on
                              the result - proves the extraction layout is
                              loader-ready even without a matching ROM
      [--strict]              exit 1 when a catalogued game is present but its
                              ROM dump does not match (definitive-correction
                              mode: surfaces mismatched dumps as failures)
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "scripts" / "headless_record"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import rom_target  # noqa: E402  (cross-validation only)
from mep_lint import normalize_rom_core_name  # noqa: E402

# ---------------------------------------------------------------------------
# No-Intro sha1 mirror of MepPackManager::ComputeNoIntroSha1 (ADR-0044): the
# SHA1 of exactly the PRG+CHR the iNES header declares, header (16 bytes) and
# optional trainer (512 bytes, flags6 bit 2) excluded. NES 2.0 size MSBs from
# header byte 9 are OR'd into the unit counts exactly as the core does.
# ---------------------------------------------------------------------------


def no_intro_sha1(data: bytes) -> str:
    size = len(data)
    offset = 0
    if size >= 16 and data[:4] == b"NES\x1a":
        offset = 16
        if data[6] & 0x04:
            offset += 512
        prg_units = data[4]
        chr_units = data[5]
        if (data[7] & 0x0C) == 0x08 and (data[9] & 0x0F) != 0x0F and (data[9] >> 4) != 0x0F:
            prg_units |= (data[9] & 0x0F) << 8
            chr_units |= (data[9] >> 4) << 8
        declared = offset + prg_units * 0x4000 + chr_units * 0x2000
        if declared > offset and declared < size:
            size = declared
    if offset > size:
        offset = size
    return hashlib.sha1(data[offset:size]).hexdigest().upper()


# ---------------------------------------------------------------------------
# Client mirrors (the C# in UI/Logic is normative and unit-tested; this is the
# I/O-only harness mirror, same relationship as mep_lint.py to the C++ rules).
# ---------------------------------------------------------------------------


def normalize_zip_path(path: str):
    work = path.replace("\\", "/")
    if work.startswith("/") or ":" in work:
        return None
    if any(ord(c) < 0x20 for c in work):
        return None
    parts = []
    for part in work.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)
    return "/".join(parts) or None


def find_pack_root(names, rom_name):
    """LegacyHdPackInstall.FindPackRoot: the parent prefix of every hires.txt
    entry, preferring a prefix whose leaf folder equals the loaded ROM name,
    else the shallowest ("" = zip root). None when no hires.txt at all."""
    hire_roots = []
    for name in names:
        leaf = name.rsplit("/", 1)[-1]
        if leaf.lower() != "hires.txt":
            continue
        prefix = "" if "/" not in name else name.rsplit("/", 1)[0] + "/"
        if prefix not in hire_roots:
            hire_roots.append(prefix)
    if not hire_roots:
        return None
    for prefix in hire_roots:
        leaf = prefix.rstrip("/").rsplit("/", 1)[-1]
        if leaf.lower() == rom_name.lower():
            return prefix
    return min(hire_roots, key=len)


def find_nested_zip(names):
    """LegacyHdPackInstall.FindNestedZip: the single root-level '.zip' entry
    of a wrapper zip (the "UnZipMeFirst"-style Drive release), None on zero
    or several."""
    candidate = None
    for name in names:
        if not name or "/" in name:
            continue
        if not name.lower().endswith(".zip"):
            continue
        if candidate is not None:
            return None
        candidate = name
    return candidate


def _entries(zf: zipfile.ZipFile):
    return [n for n in zf.namelist() if not n.endswith("/")]


def extract_legacy_pack(pack_zip: Path, target: Path, rom_name: str):
    """Extract the pack into <target> so hires.txt lands directly there -
    the layout HdTilePack::LoadForRom reads. Raises ValueError with a reason
    when the zip is not a legacy HD pack (zip-slip, no hires.txt, ambiguous)."""
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pack_zip) as outer:
        names = []
        by_name = {}
        for entry in _entries(outer):
            norm = normalize_zip_path(entry)
            if norm is None:
                raise ValueError(f"zip entry escapes the pack root: {entry!r}")
            names.append(norm)
            by_name[norm] = entry
        if not names:
            raise ValueError("zip is empty")

        root = find_pack_root(names, rom_name)
        inner = None
        if root is None:
            nested = find_nested_zip(names)
            if nested is None:
                raise ValueError("not a legacy HD pack (no hires.txt)")
            inner = outer.read(nested)
            with zipfile.ZipFile(io_bytes(inner)) as inner_zip:
                names = []
                by_name = {}
                for entry in _entries(inner_zip):
                    norm = normalize_zip_path(entry)
                    if norm is None:
                        raise ValueError(f"zip entry escapes the pack root: {entry!r}")
                    names.append(norm)
                    by_name[norm] = entry
                if not names:
                    raise ValueError("zip is empty")
                root = find_pack_root(names, rom_name)
                if root is None:
                    raise ValueError("not a legacy HD pack (no hires.txt)")
                _extract_under(inner_zip, by_name, root, target)
        else:
            _extract_under(outer, by_name, root, target)


def _extract_under(zf, by_name, root, target):
    for norm, entry in by_name.items():
        if not norm.startswith(root):
            continue  # outside the pack root (banner art, README, ...)
        rel = norm[len(root):]
        if not rel:
            continue
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(entry))


def io_bytes(b: bytes):
    import io
    return io.BytesIO(b)


# ---------------------------------------------------------------------------
# Catalog + coverage
# ---------------------------------------------------------------------------


def load_catalog(path: Path):
    import json
    return json.load(open(path))["packs"]


def find_catalog_match(packs, sha1):
    for p in packs:
        rom = p.get("rom") or {}
        s = (rom.get("sha1") or "").strip().upper()
        if s and s == sha1:
            return p
    return None


_STOP_TOKENS = {"the", "and"}


def _game_tokens(name: str):
    #Word-order/separator-insensitive token multiset: "Legend of Zelda, The
    #(USA)" and "The Legend of Zelda (USA)" are the same game, while "Super
    #Mario Bros. 3" is NOT the same game as "Super Mario Bros" (subset
    #matching would collapse the sequel into the original - that is why this
    #is a multiset equality, not containment).
    norm = normalize_rom_core_name(name)
    return sorted(re.sub(r"[^a-z0-9 ]", "", norm).split())


def same_game(a: str, b: str) -> bool:
    ta, tb = _game_tokens(a), _game_tokens(b)
    if not ta or not tb:
        return False
    return ta == tb


def find_catalog_entry_for_game(packs, game_norm):
    return [p for p in packs if same_game(p.get("game") or "", game_norm)]


def rom_sha1(path: Path) -> str:
    return no_intro_sha1(path.read_bytes())


def coverage(roms, packs):
    rows = []
    for rom in roms:
        sha1 = rom_sha1(rom)
        match = find_catalog_match(packs, sha1)
        stem_norm = normalize_rom_core_name(rom.stem)
        cross = None
        tgt = rom_target.NO_INTRO_TARGETS.get(stem_norm) or rom_target.NO_INTRO_TARGETS.get(
            rom_target.normalize_game_name(rom.stem))
        if tgt:
            cross = "MATCH" if tgt["sha1"] == sha1 else "DIFFERS"
        reason = None
        if match:
            verdict = f"MATCH -> {match['name']}"
        else:
            for_game = find_catalog_entry_for_game(packs, stem_norm)
            if for_game and any((p.get("rom") or {}).get("sha1") for p in for_game):
                wants = next((p["rom"]["sha1"] for p in for_game if p["rom"].get("sha1")), "?")
                reason = f"no match: catalog has '{for_game[0]['game']}' but targets a different dump (wants {wants})"
            elif for_game:
                reason = f"no match: '{for_game[0]['game']}' is catalogued but listable-only (no rom.sha1)"
            else:
                reason = "no match: no catalog entry carries this dump's hash"
            verdict = reason
        rows.append((rom, sha1, cross, verdict))
    return rows


# ---------------------------------------------------------------------------
# Install + headless load
# ---------------------------------------------------------------------------


def acquire_pack(entry, args, work: Path) -> Path:
    """Download (or reuse a local zip) the artifact for a matched entry and
    return its path, verifying the sha256 the catalog declares."""
    import urllib.parse
    url = entry["url"]
    declared = entry.get("sha256") or ""
    if args.pack:
        local = Path(args.pack)
    else:
        base = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
        local = None
        if args.pack_dir:
            cand = Path(args.pack_dir) / base
            if cand.exists():
                local = cand
        if local is None:
            out = work / f"dl-{entry['game']}.zip"
            env = dict(os.environ)
            #macOS framework Python's bundled OpenSSL does not load the system
            #cert store; fetch_pack.py (urllib) then fails with
            #CERTIFICATE_VERIFY_FAILED. Point it at certifi's bundle when
            #available, mirroring the C# client, which uses the system store.
            try:
                import certifi
                env["SSL_CERT_FILE"] = certifi.where()
            except ImportError:
                pass
            subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "fetch_pack.py"), url, str(out),
                 "--max-bytes", "314572800"],
                cwd=str(REPO_ROOT), env=env, check=True)
            local = out
    actual = hashlib.sha256(local.read_bytes()).hexdigest()
    if declared:
        if actual != declared.lower():
            raise ValueError(
                f"sha256 mismatch for {local.name}: catalog declares {declared}, artifact is {actual} "
                f"(catalog data stale until revalidation, or wrong artifact)")
    return local


def install_and_load(rom: Path, args, work: Path) -> str:
    """Zeroed-state install + headless load for one ROM; returns a PASS/FAIL
    verdict string."""
    home = work / "out" / "mesen-home"
    # ALWAYS from zero: wipe both the legacy and MEP install locations.
    shutil.rmtree(work, ignore_errors=True)
    (home / "HdPacks").mkdir(parents=True, exist_ok=True)
    (home / "EnhancementPacks").mkdir(parents=True, exist_ok=True)

    packs = load_catalog(args.catalog)
    sha1 = rom_sha1(rom)
    entry = find_catalog_match(packs, sha1)
    if entry is None:
        return "SKIP (no catalog match)"
    rom_name = rom.stem

    try:
        pack = acquire_pack(entry, args, work)
    except Exception as e:
        return f"FAIL (download/verify): {e}"

    try:
        extract_legacy_pack(pack, home / "HdPacks" / rom_name, rom_name)
    except ValueError as e:
        return f"FAIL (extract): {e}"
    if not (home / "HdPacks" / rom_name / "hires.txt").exists():
        return "FAIL (extract): hires.txt not at HdPacks/<rom>/hires.txt"

    out_prefix = work / "out" / "x"
    log = subprocess.run(
        [str(HARNESS), str(rom), "2", str(out_prefix), "log"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
    text = log.stdout + log.stderr

    #Positive load signal for the loose NES path is the log added in
    #NesConsole.cpp::LoadHdPack ("[MEP] textures: loaded loose NES HD pack
    #from HdPacks/<rom>/hires.txt"); MEP-container installs log the
    #"[MEP] textures: loaded NES HD pack from '...'" line instead.
    loaded = ("[MEP] textures: loaded loose NES HD pack from HdPacks/" in text
              or "[MEP] textures: loaded NES HD pack from '" in text)
    if log.returncode != 0 or not loaded:
        return f"FAIL (load): headless_record exit={log.returncode}, loaded={loaded}"
    #Pack-content errors (missing <background> PNG, condition types the NES
    #loader rejects on backgrounds) are PACK quality, not install failures:
    #mep_lint tolerates them as warnings and the tiles that do load apply.
    #Report them as a warning note so a PASS is never silent about them.
    content_errors = [ln for ln in text.splitlines()
                      if "[HDPack - Line" in ln or "[HDPack] PNG file" in ln]
    if content_errors:
        note = " ; ".join(content_errors[:3])
        return f"PASS (pack has {len(content_errors)} runtime error line(s) - mep_lint tolerates them: {note})"
    return "PASS"


def verify_pack_only(pack_zip: Path, args, work: Path):
    home = work / "out" / "mesen-home"
    shutil.rmtree(work, ignore_errors=True)
    (home / "HdPacks" / "Probe").mkdir(parents=True, exist_ok=True)
    extract_legacy_pack(pack_zip, home / "HdPacks" / "Probe", "Probe")
    print(f"extracted to {home}/HdPacks/Probe/")
    for p in sorted((home / "HdPacks" / "Probe").rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(home / 'HdPacks' / 'Probe')}")
    r = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "mep_lint.py"),
                        str(home / "HdPacks" / "Probe")], cwd=str(REPO_ROOT), capture_output=True, text=True)
    print(r.stdout)
    return r.returncode


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roms_dir")
    ap.add_argument("--catalog", type=Path, default=REPO_ROOT / "docs" / "community-packs.json")
    ap.add_argument("--pack", type=Path)
    ap.add_argument("--pack-dir", type=Path)
    ap.add_argument("--work", type=Path, default=REPO_ROOT / ".cache" / "verify-from-zero")
    ap.add_argument("--coverage-only", action="store_true")
    ap.add_argument("--rom", help="restrict to one ROM file (name or path substring)")
    ap.add_argument("--verify-pack-only", type=Path)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)

    if args.verify_pack_only:
        return verify_pack_only(args.verify_pack_only, args, args.work)

    if not HARNESS.exists():
        print(f"FAIL: {HARNESS} not built (run 'make capture-tool' first)", file=sys.stderr)
        return 1

    packs = load_catalog(args.catalog)
    roms = sorted([p for p in Path(args.roms_dir).rglob("*") if p.suffix.lower() in (".nes", ".sfc", ".smc")])
    if args.rom:
        roms = [r for r in roms if args.rom in r.name or args.rom in str(r)]
    if not roms:
        print(f"no ROMs found under {args.roms_dir}", file=sys.stderr)
        return 1

    # Wipe the catalog cache too, so a client run right after always re-reads
    # from zero (the harness itself reads the repo catalog file).
    for cache in REPO_ROOT.glob(".cache/community-packs.json*"):
        cache.unlink(missing_ok=True)

    rows = coverage(roms, packs)
    strict_fail = 0
    print(f"--- coverage ({len(roms)} ROMs vs {len(packs)} catalog entries) ---")
    for rom, sha1, cross, verdict in rows:
        line = f"  {rom.name:46s} {sha1[:12]}  {verdict}"
        if cross:
            line += f"  [mirror:{cross}]"
        print(line)
        if cross == "DIFFERS" or (args.strict and verdict.startswith("no match") and "different dump" in verdict):
            strict_fail += 1

    if args.coverage_only:
        print(f"coverage done (strict mismatches: {strict_fail})")
        return 0

    print("--- install + headless load (always from zero) ---")
    results = []
    for rom, _, _, verdict in rows:
        if not verdict.startswith("MATCH"):
            results.append((rom, verdict))
            continue
        result = install_and_load(rom, args, args.work)
        results.append((rom, result))
        print(f"  {rom.name:46s} {result}")
        # fresh scratch per ROM so each install starts zeroed
        shutil.rmtree(args.work, ignore_errors=True)

    failed = [r for _, r in results if r.startswith("FAIL")]
    skipped = [r for _, r in results if r.startswith("SKIP")]
    passed = [r for _, r in results if r.startswith("PASS")]
    print(f"--- result: PASS={len(passed)} skip={len(skipped)} fail={len(failed)} strict={strict_fail} ---")
    return 1 if failed or strict_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
