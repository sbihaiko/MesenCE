#!/usr/bin/env python3
"""validate_palette_variants — headless proof for F5.4b (ADR-0050 step b):
HdPackBuilder::ProcessTile used to funnel every real-palette sighting of a
tile shape that only had a DefaultTile wildcard entry into that one neutral
entry, so the bootstrap capture only ever recorded one palette per shape.
This checks that a real gameplay recording now captures several distinct
palette-specific HdPackTileInfo entries for the same tile shape instead.

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
CAPTURE_SECONDS = 20
TILE_RE = re.compile(r"^(\[(?P<cond>[^\]]*)\])?<tile>(?P<body>.*)$")


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


def run_checks(hires: Path) -> list:
    checks = [(f"hires.txt gerado ({hires})", hires.exists())]

    shapes = group_palettes_by_shape(hires)
    checks.append((f"tiles capturados ({len(shapes)} shapes distintos)", len(shapes) > 0))

    multi_palette_shapes = {k: v for k, v in shapes.items() if len(v) > 1}
    max_variants = max((len(v) for v in shapes.values()), default=0)
    checks.append(
        (
            "pelo menos 1 tile shape com mais de 1 paleta distinta capturada "
            f"({len(multi_palette_shapes)}/{len(shapes)} shapes com variantes, "
            f"máximo {max_variants} paletas num único shape)",
            len(multi_palette_shapes) > 0,
        )
    )
    return checks


def main() -> int:
    if not ROM.exists():
        print(f"FAIL: rom não encontrada em {ROM} (necessária para esta validação)")
        return 1

    tool = ensure_capture_tool()
    if not tool.exists():
        print(f"FAIL: {tool} continua ausente após 'make capture-tool'")
        return 1
    print(f"PASS: headless_record disponível em {tool}")

    with tempfile.TemporaryDirectory(prefix="hdpack-palette-") as tmp:
        hires = record_hdpack(tool, Path(tmp))
        checks = run_checks(hires)

    ok = True
    for name, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
        ok = ok and passed

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
