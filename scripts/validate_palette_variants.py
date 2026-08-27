#!/usr/bin/env python3
"""validate_palette_variants — headless proof for F5.4b (ADR-0050 step b):
HdPackBuilder::ProcessTile already gave every distinct (shape, PaletteColors)
combination its own HdPackTileInfo (the old "DefaultTile wildcard" fallback
was dead code - GetKey(true) sentinels PaletteColors to 0xFFFFFFFF, a value
no real PPU palette word ever produces, so it could never match anything in
_tileUsageCount). What was genuinely unbounded was per-shape growth: a
mostly/fully flat tile shape renders identically under any background
palette, so unrelated screen state alone can rack up dozens of "distinct"
PaletteColors sightings for one shape with no artistic value - measured on a
pre-cap 20s roms/Zelda.nes hdpack recording, a single all-zero blank-tile
shape alone reached 71 variants while the rest of the corpus sat at a median
of 14 (p99 27). MaxPaletteVariantsPerTile (Core/NES/HdPacks/HdPackBuilder.h)
bounds that long tail.

This checks BOTH halves of the fix against a real gameplay recording:
  1) capture still produces several distinct palette-specific entries for the
     same tile shape (the pre-existing, non-regressed capability), and
  2) no single tile shape ever exceeds MaxPaletteVariantsPerTile (the actual
     structural guarantee this task adds - provably false pre-fix, since the
     71-variant blank-tile shape above exceeds any sane cap), with at least
     one shape reaching the cap so the check is known to engage on real data
     rather than passing vacuously because nothing ever gets close to it.

Reproducing the pre-fix baseline this cap is derived from (no double-build
baked into this script, to keep it to a single `make capture-tool` + one
recording):
    git checkout <base-commit> -- Core/NES/HdPacks/HdPackBuilder.cpp Core/NES/HdPacks/HdPackBuilder.h
    make capture-tool
    ./scripts/headless_record roms/Zelda.nes 20 /tmp/pre hdpack
    # group /tmp/pre-hdpack/hires.txt <tile> lines by TileData like
    # group_palettes_by_shape() below and look at the per-shape variant counts
    git checkout HEAD -- Core/NES/HdPacks/HdPackBuilder.cpp Core/NES/HdPacks/HdPackBuilder.h
    make capture-tool

Builds scripts/headless_record via `make capture-tool` if missing, records
roms/Zelda.nes (a CHR RAM title, per F5.2's prior validation) for a fixed
duration with the "hdpack" flag (HdPackBuilder::StartRecordHdPack -> gameplay
capture only, no static ROM export - so every captured entry is a real,
non-default palette sighting), then groups the resulting hires.txt <tile>
lines by tile shape the same way scripts/mep_compare.py does (CHR-RAM key =
32-hex TileData bytes; PaletteColors is the per-sighting palette).

Usage: python3 scripts/validate_palette_variants.py
Prints PASS/FAIL per check; exits non-zero if any check fails.
"""
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROM = REPO_ROOT / "roms" / "Zelda.nes"
HEADER = REPO_ROOT / "Core" / "NES" / "HdPacks" / "HdPackBuilder.h"
CAPTURE_SECONDS = 20
TILE_RE = re.compile(r"^(\[(?P<cond>[^\]]*)\])?<tile>(?P<body>.*)$")
CAP_RE = re.compile(r"MaxPaletteVariantsPerTile\s*=\s*(\d+)\s*;")


def read_cap() -> int:
    """The MaxPaletteVariantsPerTile value straight from the header, so this
    validator always checks against the constant the build actually used."""
    match = CAP_RE.search(HEADER.read_text())
    if not match:
        raise RuntimeError(f"MaxPaletteVariantsPerTile not found in {HEADER}")
    return int(match.group(1))


def ensure_capture_tool() -> Path:
    tool = REPO_ROOT / "scripts" / "headless_record"
    if not tool.exists():
        print(f"[build] {tool} missing, running 'make capture-tool'...")
        subprocess.run(["make", "capture-tool"], cwd=REPO_ROOT, check=True)
    return tool


def record_hdpack(tool: Path, out_dir: Path) -> Path:
    prefix = out_dir / "zelda"
    subprocess.run(
        [str(tool), str(ROM), str(CAPTURE_SECONDS), str(prefix), "hdpack"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    hires = out_dir / "zelda-hdpack" / "hires.txt"
    if not hires.exists():
        raise RuntimeError(f"{hires} was not produced by the recording")
    return hires


def group_palettes_by_shape(hires: Path) -> dict:
    """tile-shape (32-hex TileData) -> set of distinct PaletteColors seen."""
    shapes = defaultdict(set)
    for line in hires.read_text(errors="replace").splitlines():
        match = TILE_RE.match(line.strip())
        if not match:
            continue
        fields = match.group("body").split(",")
        if len(fields) < 5 or len(fields[1]) != 32:
            continue  # CHR ROM index keys (not this CHR-RAM title) are out of scope
        shapes[fields[1].upper()].add(fields[2].upper())
    return shapes


def _multi_palette_check(shapes: dict) -> tuple:
    """At least 1 tile shape captured more than one distinct palette - the
    pre-existing, non-regressed capability (see module docstring)."""
    multi_palette_shapes = {k: v for k, v in shapes.items() if len(v) > 1}
    max_variants = max((len(v) for v in shapes.values()), default=0)
    return (
        "at least 1 tile shape captured more than one distinct palette "
        f"({len(multi_palette_shapes)}/{len(shapes)} shapes with variants, "
        f"max {max_variants} palettes in a single shape)",
        len(multi_palette_shapes) > 0,
    )


def _cap_not_exceeded_check(variant_counts: list, cap: int) -> tuple:
    """Discriminating check: provably false on the pre-fix build (a single
    all-zero blank-tile shape reached 71 variants in the reproduction steps
    in the module docstring), so passing here is real evidence the cap in
    HdPackBuilder::CaptureOrCapPaletteVariant is actually enforced."""
    max_variants = max(variant_counts, default=0)
    return (
        f"no tile shape exceeds MaxPaletteVariantsPerTile ({cap}) "
        f"(max observed: {max_variants})",
        max_variants <= cap,
    )


def _cap_reached_check(variant_counts: list, cap: int) -> tuple:
    """The cap is actually exercised by this recording (not vacuously true
    because no shape ever gets close to it)."""
    shapes_at_cap = sum(1 for c in variant_counts if c == cap)
    return (
        f"cap effectively reached by at least 1 real shape "
        f"({shapes_at_cap} shape(s) with exactly {cap} variants)",
        shapes_at_cap > 0,
    )


def run_checks(hires: Path, cap: int) -> list:
    checks = [(f"hires.txt generated ({hires})", hires.exists())]

    shapes = group_palettes_by_shape(hires)
    checks.append((f"tiles captured ({len(shapes)} distinct shapes)", len(shapes) > 0))

    variant_counts = [len(v) for v in shapes.values()]
    checks.append(_multi_palette_check(shapes))
    checks.append(_cap_not_exceeded_check(variant_counts, cap))
    checks.append(_cap_reached_check(variant_counts, cap))
    return checks


def main() -> int:
    if not ROM.exists():
        print(f"FAIL: rom not found at {ROM} (required for this validation)")
        return 1

    cap = read_cap()
    print(f"PASS: MaxPaletteVariantsPerTile read from {HEADER} = {cap}")

    tool = ensure_capture_tool()
    if not tool.exists():
        print(f"FAIL: {tool} still missing after 'make capture-tool'")
        return 1
    print(f"PASS: headless_record available at {tool}")

    with tempfile.TemporaryDirectory(prefix="hdpack-palette-") as tmp:
        hires = record_hdpack(tool, Path(tmp))
        checks = run_checks(hires, cap)

    ok = True
    for name, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
        ok = ok and passed

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
