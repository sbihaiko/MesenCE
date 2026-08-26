#!/usr/bin/env python3
"""test_mep_compare_auto_palettes — fixture-based check for AC-4: proves
`mep_compare.py`'s `stats["auto"]` dict now carries `palettes_per_shape`
(previously only computed for the `artist` side).

No emulator, no ROM, no build: writes a small real NES-shaped HD pack
fixture to disk (`<tile>` lines with two distinct CHR shapes, one of them
seen under two distinct palettes — the exact "several palettes captured for
one shape" situation F5.4b's capture-side fix produces) and self-compares
it through `mep_compare.main()` directly, then inspects the JSON it wrote.

The existing golden pack at `docs/specs/golden/mep/textures` is GB-shaped
(4-hex-char palette field) and is incompatible with `render_original`'s
NES-only 8-hex-char palette decoding (a pre-existing, unrelated limitation
of `mep_compare.py` — out of scope here), so this check uses its own
on-disk NES-shaped fixture instead.

Framework-free: prints PASS/FAIL per case, exits non-zero on any failure
(see scripts/AGENTS.md's harness convention).

Uso: python3 scripts/test_mep_compare_auto_palettes.py
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image

SCRIPTS_DIR = Path(__file__).resolve().parent

# Two distinct 16-byte (32 hex char) NES CHR shapes; SHAPE_A is captured
# under two distinct 8-hex-char palettes, SHAPE_B under just one -- mirrors
# the multi-palette-per-shape capture F5.4b's HdPackBuilder fix enables.
SHAPE_A = "3C004200B900A500B900A50042003C00"
SHAPE_B = "F300F300F000F000F000F000F000F000"
PAL_1 = "0F001A2C"
PAL_2 = "0F102636"


def _load_mep_compare():
    spec = importlib.util.spec_from_file_location("mep_compare", SCRIPTS_DIR / "mep_compare.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_fixture(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (24, 8), (0, 0, 0, 0))
    px = img.load()
    for tile_x, color in ((0, (200, 40, 40, 255)), (8, (40, 200, 40, 255)), (16, (40, 40, 200, 255))):
        for y in range(8):
            for x in range(tile_x, tile_x + 8):
                px[x, y] = color
    img.save(folder / "tiles.png")
    lines = [
        "<ver>200",
        "<system>nes",
        "<scale>1",
        "<img>tiles.png",
        f"<tile>0,{SHAPE_A},{PAL_1},0,0,1,N",
        f"<tile>0,{SHAPE_A},{PAL_2},8,0,1,N",
        f"<tile>0,{SHAPE_B},{PAL_1},16,0,1,N",
    ]
    (folder / "hires.txt").write_text("\n".join(lines) + "\n")
    return folder


def _run_self_compare(mep_compare, pack_dir: Path, out_dir: Path) -> dict:
    argv = ["mep_compare.py", str(pack_dir), str(pack_dir), str(out_dir),
            "--name", "selftest", "--samples", "4"]
    rc = mep_compare.main(argv)
    if rc != 0:
        raise RuntimeError(f"mep_compare.main() returned non-zero exit code {rc}")
    return json.loads((out_dir / "selftest.json").read_text())


def check_auto_reports_palettes_per_shape(stats: dict) -> bool:
    auto = stats.get("auto")
    has_key = isinstance(auto, dict) and "palettes_per_shape" in auto
    print(("PASS" if has_key else "FAIL") + ": stats['auto'] contains 'palettes_per_shape'")
    if not has_key:
        return False
    value = auto["palettes_per_shape"]
    is_numeric = isinstance(value, (int, float))
    print(("PASS" if is_numeric else "FAIL") + f": stats['auto']['palettes_per_shape'] is numeric ({value!r})")
    return is_numeric


def check_auto_palettes_per_shape_value(stats: dict) -> bool:
    # Fixture has 3 distinct (shape, palette) keys over 2 distinct shapes:
    # SHAPE_A x {PAL_1, PAL_2} and SHAPE_B x {PAL_1} -> 3 / 2 = 1.5.
    expected = 1.5
    value = stats["auto"]["palettes_per_shape"]
    ok = value == expected
    print(("PASS" if ok else "FAIL") + f": stats['auto']['palettes_per_shape'] == {expected} (got {value!r})")
    return ok


def check_artist_still_reports_palettes_per_shape(stats: dict) -> bool:
    artist = stats.get("artist")
    ok = isinstance(artist, dict) and "palettes_per_shape" in artist
    print(("PASS" if ok else "FAIL") + ": stats['artist'] still contains 'palettes_per_shape' (no regression)")
    return ok


def main() -> int:
    mep_compare = _load_mep_compare()
    with tempfile.TemporaryDirectory(prefix="mep_compare_auto_palettes_") as tmp:
        tmp_path = Path(tmp)
        pack_dir = _build_fixture(tmp_path / "pack")
        out_dir = tmp_path / "out"
        stats = _run_self_compare(mep_compare, pack_dir, out_dir)
        results = [
            check_auto_reports_palettes_per_shape(stats),
            check_auto_palettes_per_shape_value(stats),
            check_artist_still_reports_palettes_per_shape(stats),
        ]

    if all(results):
        print("PASS: all checks passed")
        return 0
    print("FAIL: one or more checks failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
