#!/usr/bin/env python3
"""test_mep_compare_auto_palettes — fixture-based check for AC-4: proves
`mep_compare.py`'s `stats["auto"]` dict now carries `palettes_per_shape`
(previously only computed for the `artist` side).

No emulator, no ROM, no build: self-compares the shared NES golden fixture
at `docs/specs/golden/mep-nes/textures` (ADR-0136) against itself through
`mep_compare.main()` directly, then inspects the JSON it wrote. That golden
is the shared NES-shaped fixture sibling to the GB golden at
`docs/specs/golden/mep/` -- it captures one CHR shape under two distinct
8-hex-char NES palettes and a second shape under just one, the exact
"several palettes captured for one shape" situation F5.4b's capture-side
fix produces (see `docs/specs/golden/mep-nes/textures/hires.txt`).

Framework-free: prints PASS/FAIL per case, exits non-zero on any failure
(see scripts/AGENTS.md's harness convention).

Uso: python3 scripts/test_mep_compare_auto_palettes.py
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
GOLDEN_TEXTURES = SCRIPTS_DIR.parent / "docs" / "specs" / "golden" / "mep-nes" / "textures"


def _load_mep_compare():
    spec = importlib.util.spec_from_file_location("mep_compare", SCRIPTS_DIR / "mep_compare.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    # docs/specs/golden/mep-nes/textures/hires.txt has 3 distinct (shape,
    # palette) <tile> keys over 2 distinct CHR shapes: one shape captured
    # under two palettes (PAL_1, PAL_2), the other under just PAL_1 ->
    # 3 / 2 = 1.5. This mirrors the count the inline fixture this test
    # previously hand-rolled produced -- verified against the golden's
    # actual tile lines, not merely carried over unchanged.
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
        out_dir = Path(tmp) / "out"
        stats = _run_self_compare(mep_compare, GOLDEN_TEXTURES, out_dir)
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
