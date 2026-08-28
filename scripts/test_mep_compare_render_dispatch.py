#!/usr/bin/env python3
"""test_mep_compare_render_dispatch — framework-free check for ADR-0136:
`mep_compare.py`'s `render_original` gains a `system` keyword and dispatches
to per-system tile+palette decoding instead of always assuming NES.

Proves (AC-1, AC-2):
  * `render_original` decodes `nes`, `gb`, `gbc`, and `sms` fixtures shaped
    per docs/specs/hires-gbsms-v1-draft.md S3.2 without raising;
  * an unsupported `<system>` value (e.g. `gba`), or a palette hex string of
    the wrong width for the declared system, raises a `ValueError` naming
    the rejected system and the supported list, before any per-tile decode
    work touches the (possibly malformed) tile data.

No emulator, no ROM, no build: calls `render_original` directly with inline
hex fixtures. Framework-free: prints PASS/FAIL per case, exits non-zero on
any failure (see scripts/AGENTS.md's harness convention).

Usage: python3 scripts/test_mep_compare_render_dispatch.py
"""
import importlib.util
import sys
from pathlib import Path

from PIL import Image

SCRIPTS_DIR = Path(__file__).resolve().parent

# One valid (chr_hex, pal_hex) fixture per supported system, shaped per
# hires-gbsms-v1-draft.md S3.2's tile-data/palette-key widths:
#   nes: 16B 2bpp planar CHR (32 hex) + 4x NES palette index (8 hex)
#   gb:  16B 2bpp interleaved tile (32 hex) + "TTPP" BGP/OBPx field (4 hex)
#   gbc: 16B 2bpp interleaved tile (32 hex) + TT + 4x RGB555 BE (18 hex)
#   sms: 32B 4bpp planar tile (64 hex) + TT + CRAM base + 16 RGB222 (36 hex)
FIXTURES = {
    "nes": ("FF00FF00FF00FF00" + "0F0F0F0F0F0F0F0F", "0F001A2C"),
    "gb": ("FF0F" * 8, "0190"),
    "gbc": ("FF0F" * 8, "00" + "7FFF00001F0003E0"),
    "sms": ("FF000FF0" * 8, "0000" + "3F" * 16),
}

UNSUPPORTED_SYSTEM = "gba"
SUPPORTED_LIST = "nes, gb, gbc, sms"


def _load_mep_compare():
    spec = importlib.util.spec_from_file_location("mep_compare", SCRIPTS_DIR / "mep_compare.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_decodes_every_supported_system(mep_compare) -> bool:
    ok = True
    for system, (chr_hex, pal_hex) in FIXTURES.items():
        try:
            img = mep_compare.render_original(chr_hex, pal_hex, system=system)
            passed = isinstance(img, Image.Image) and img.size == (8, 8)
        except Exception as exc:  # noqa: BLE001 - report, don't hide, the failure
            passed, img = False, exc
        print(("PASS" if passed else "FAIL") + f": render_original decodes system={system!r} without raising ({img!r})")
        ok = ok and passed
    return ok


def check_rejects_unsupported_system(mep_compare) -> bool:
    nes_chr, nes_pal = FIXTURES["nes"]
    try:
        mep_compare.render_original(nes_chr, nes_pal, system=UNSUPPORTED_SYSTEM)
        print(f"FAIL: render_original(system={UNSUPPORTED_SYSTEM!r}) did not raise")
        return False
    except (ValueError, SystemExit) as exc:
        message = str(exc)
        names_system = UNSUPPORTED_SYSTEM in message
        names_supported = SUPPORTED_LIST in message
        ok = names_system and names_supported
        print(("PASS" if ok else "FAIL") + f": unsupported system raises naming rejected system and supported list ({message!r})")
        return ok


def check_rejects_before_per_tile_work(mep_compare) -> bool:
    # An empty chr_hex is valid to bytes.fromhex() (yields b""), so any
    # exception here is proof the system/width check ran and raised *before*
    # the decode loop tried to index into the (empty) tile data.
    try:
        mep_compare.render_original("", "00", system=UNSUPPORTED_SYSTEM)
        print("FAIL: render_original with empty chr_hex + unsupported system did not raise")
        return False
    except ValueError as exc:
        ok = UNSUPPORTED_SYSTEM in str(exc)
        print(("PASS" if ok else "FAIL") + f": unsupported system rejected before touching per-tile data ({exc!r})")
        return ok
    except IndexError:
        print("FAIL: render_original ran per-tile decode work (IndexError) before validating <system>")
        return False


def check_rejects_wrong_width_palette(mep_compare) -> bool:
    nes_chr, _ = FIXTURES["nes"]
    try:
        mep_compare.render_original(nes_chr, "00", system="nes")
        print("FAIL: render_original(system='nes') with a too-short palette did not raise")
        return False
    except ValueError as exc:
        message = str(exc)
        ok = "nes" in message and "8-hex" in message and "got 2" in message
        print(("PASS" if ok else "FAIL") + f": wrong-width palette for a valid system names the expected and actual widths ({message!r})")
        return ok


def check_sms_tiles_parse(mep_compare) -> bool:
    # An SMS tile is 32 bytes = 64 hex (draft S3.2); before ADR-0136 §6 the
    # parser hard-coded the NES 32-hex width and silently dropped every SMS
    # tile, so the comparator "worked" on SMS packs by comparing nothing.
    import tempfile
    from pathlib import Path
    sms_chr, sms_pal = FIXTURES["sms"]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "hires.txt").write_text(
            "<ver>200\n<scale>1\n<img>tiles.png\n"
            f"<tile>0,{sms_chr},{sms_pal},0,0,1,N\n"
            "<system>sms\n")  # header deliberately after the tile line
        pack = mep_compare.Pack(folder)
        ok = pack.system == "sms" and len(pack.tiles) == 1
        print(("PASS" if ok else "FAIL") + f": Pack parses a 64-hex SMS tile with a late <system> header (system={pack.system!r}, tiles={len(pack.tiles)})")
        return ok


def main() -> int:
    mep_compare = _load_mep_compare()
    results = [
        check_decodes_every_supported_system(mep_compare),
        check_rejects_unsupported_system(mep_compare),
        check_sms_tiles_parse(mep_compare),
        check_rejects_before_per_tile_work(mep_compare),
        check_rejects_wrong_width_palette(mep_compare),
    ]
    if all(results):
        print("PASS: all checks passed")
        return 0
    print("FAIL: one or more checks failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
