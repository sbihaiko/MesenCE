#!/usr/bin/env python3
"""Framework-free checks for `mep_addition` — ADR-0196's `<addition>` tag and
its synthetic target key (Slice F12.5).

Everything under test is a pure decision over strings and ints, so these checks
need no pack, no ROM on disk beyond a 16-byte iNES header written into a temp
file, and no emulator. What they pin down:

* the reserved CHR RAM pattern round-trips through `chr_ram_target` /
  `chr_ram_ordinal`, and nothing else is mistaken for it;
* the `$0D` palette evidence check reports what it saw, and the ordinal is
  1-based so the 0th key is never sixteen zero bytes;
* the CHR ROM target lands past the end of CHR, read off the iNES header in
  both the plain and the NES 2.0 form;
* `addition_line` / `parse_addition` round-trip, and `ignorePalette` is never
  written;
* `target_verdict` refuses every key ADR-0196 §3 refuses, and
  `plan_sheet_additions` refuses a sidecar that does not back its own tag.

Usage: python3 scripts/test_mep_addition.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import mep_addition as A  # noqa: E402

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def check(cond, msg):
    ok(msg) if cond else fail(msg)


class Sheet:
    """The two fields `plan_sheet_additions` reads off a `mep_build.SheetDoc`."""

    def __init__(self, name, cells, additions):
        self.name = name
        self.cells = cells
        self.additions = additions


def ines(chr_units, nes2_msb=None):
    """A bare 16-byte iNES header, written to a temp file. `nes2_msb` switches
    on the NES 2.0 identifier and puts the extra nibble in byte 9."""
    data = bytearray(16)
    data[0:4] = b"NES\x1a"
    data[4] = 2
    data[5] = chr_units & 0xFF
    if nes2_msb is not None:
        data[7] = 0x08
        data[9] = (nes2_msb & 0x0F) << 4
    path = Path(tempfile.mkdtemp()) / "rom.nes"
    path.write_bytes(bytes(data))
    return path


# -- the CHR RAM half ---------------------------------------------------------

def check_chr_ram_round_trip():
    for n in (1, 2, 255, 256, 4096, A.MAX_ORDINAL):
        data = A.chr_ram_target(n)
        check(len(data) == 32, f"chr_ram_target({n}) is 32 hex digits")
        check(A.chr_ram_ordinal(data) == n, f"chr_ram_ordinal round-trips ordinal {n}")
    check(A.chr_ram_target(1) == "00000000000000010000000000000000",
          "ordinal 1's pattern carries the marker in byte 7")
    check(A.chr_ram_target(256)[30:32] == "01",
          "an ordinal above 255 spills into the high marker byte 15")


def check_ordinal_is_one_based():
    """ADR-0196 §3: the 0th reserved pattern would be sixteen zero bytes — one
    of the most-recorded tiles there is — so the ordinal starts at 1."""
    check(A.chr_ram_ordinal("0" * 32) is None,
          "sixteen zero bytes is not the reserved pattern")
    for bad in (0, -1, A.MAX_ORDINAL + 1):
        try:
            A.chr_ram_target(bad)
            fail(f"chr_ram_target({bad}) should raise")
        except A.AdditionError:
            ok(f"chr_ram_target({bad}) raises AdditionError")


def check_non_reserved_patterns_rejected():
    cases = {
        "a byte outside the marker rows": "0000000000000001000000000000FF00",
        "not 32 digits": "0001",
        "not hexadecimal": "Z" * 32,
    }
    for why, data in cases.items():
        check(A.chr_ram_ordinal(data) is None, f"chr_ram_ordinal rejects {why}")


def check_reserved_palette_evidence():
    check(A.reserved_palette_evidence(["FF36160F", "0F0F0F0F"]) == [],
          "no observed palette equals the reserved one -> no evidence")
    check(A.reserved_palette_evidence(["ff36160f", "0d0d0d0d", "0D0D0D0D"])
          == [A.RESERVED_PALETTE],
          "an observed $0D palette is reported once, case-insensitively")


# -- the CHR ROM half ---------------------------------------------------------

def check_chr_tile_count():
    check(A.chr_tile_count(ines(16)) == 8192, "16 CHR units of 8 KB are 8192 tiles")
    check(A.chr_tile_count(ines(0)) == 0, "a CHR RAM game reports no CHR tiles")
    check(A.chr_tile_count(ines(1, nes2_msb=1)) == (0x101 * 8192 // 16),
          "the NES 2.0 MSB nibble extends the CHR unit count")
    junk = Path(tempfile.mkdtemp()) / "x.nes"
    junk.write_bytes(b"not a rom")
    try:
        A.chr_tile_count(junk)
        fail("chr_tile_count on a non-iNES file should raise")
    except A.AdditionError:
        ok("chr_tile_count refuses a file that is not an iNES image")


def check_chr_rom_target():
    check(A.chr_rom_target(8192, 1) == 8192,
          "the first synthetic index is the first index past CHR")
    check(A.chr_rom_target(8192, 3) == 8194, "each further ordinal takes the next index")
    check(A.chr_rom_unmatched(8192, 8192) and A.chr_rom_unmatched(9000, 8192),
          "an index at or past the end of CHR is unmatched")
    check(not A.chr_rom_unmatched(8191, 8192),
          "the last real CHR index is matched, so it is refused")
    check(not A.chr_rom_unmatched(5, 0),
          "with no CHR ROM there is nothing to be past — no proof is available")
    try:
        A.chr_rom_target(0, 1)
        fail("chr_rom_target with no CHR tile count should raise")
    except A.AdditionError:
        ok("chr_rom_target refuses to guess without the ROM's CHR tile count")


def check_index_token():
    check(A.index_token(0x12) == "12" and A.index_token(0x412) == "0412",
          "an index is written in the shortest even number of hex digits")
    check(A.is_index_key("0412") and not A.is_index_key("0" * 32),
          "32 hex digits is pattern data, anything shorter is a CHR index")


# -- the tag ------------------------------------------------------------------

def check_addition_line_round_trip():
    anchor = ("007EFFFFE3E70000007E817E9D18FFFF", "FF36160F")
    target = (A.chr_ram_target(1), A.RESERVED_PALETTE)
    line = A.addition_line(anchor, (16, -24), target)
    check(line.startswith("<addition>"), "addition_line writes the tag")
    check(",Y" not in line.upper()[-3:] and line.count(",") == 5,
          "ignorePalette is never written (ADR-0196 §3 keeps the palette load-bearing)")
    got = A.parse_addition(line[len("<addition>"):])
    check(got == (anchor, (16, -24), target, None),
          "parse_addition round-trips anchor, offset and target")
    seven = A.parse_addition(",".join([anchor[0], anchor[1], "0", "0", target[0], target[1], "Y"]))
    check(seven[3] is True, "a seventh field is read as ignorePalette")
    for bad, why in (("a,b,c", "too few fields"), ("a,b,x,0,c,d", "a non-integer offset")):
        try:
            A.parse_addition(bad)
            fail(f"parse_addition should refuse {why}")
        except A.AdditionError:
            ok(f"parse_addition refuses {why}")


def check_target_verdict():
    good_ram = (A.chr_ram_target(1), A.RESERVED_PALETTE)
    check(A.target_verdict(good_ram, False) is None,
          "the reserved CHR RAM key passes §3")
    check("palette" in (A.target_verdict((A.chr_ram_target(1), "FF36160F"), False) or ""),
          "a CHR RAM target with a recorded palette is refused")
    check("reserved pattern" in (A.target_verdict(("0" * 32, A.RESERVED_PALETTE), False) or ""),
          "a CHR RAM target with an unreserved pattern is refused")
    check("32 hex digits" in (A.target_verdict(("2000", A.RESERVED_PALETTE), False) or ""),
          "a CHR index is refused on a CHR RAM pack")
    check(A.target_verdict(("2000", A.RESERVED_PALETTE), True) is None,
          "a CHR index passes on a CHR ROM pack when nothing bounds it")
    check(A.target_verdict(("2000", A.RESERVED_PALETTE), True, max_real_index=0x1FFF) is None,
          "index 2000 is past the pack's own largest keyed index")
    check("not past the pack's own CHR"
          in (A.target_verdict(("0412", A.RESERVED_PALETTE), True, max_real_index=0x1FFF) or ""),
          "an index the pack itself keys is not provably unmatched")
    check("keyed by CHR index" in (A.target_verdict((A.chr_ram_target(1), "0D0D0D0D"), True) or ""),
          "pattern data is refused on a CHR ROM pack")


# -- the sheet layer ----------------------------------------------------------

def ram_sheet(**over):
    cell = {"index": 6, "synthetic": True, "ordinal": 1, "pose": "pose001",
            "tiles": [{"tile": A.chr_ram_target(1), "palette": A.RESERVED_PALETTE}]}
    cell.update(over.pop("cell", {}))
    rec = {"pose": "pose001", "offsetX": 16, "offsetY": -24, "cell": 6,
           "anchor": {"node": 30, "tile": "007EFFFFE3E70000007E817E9D18FFFF",
                      "palette": "FF36160F"}}
    rec.update(over.pop("addition", {}))
    return Sheet("usr000", [cell], [rec])


def check_plan_chr_ram():
    lines, keys, errors = A.plan_sheet_additions([ram_sheet()], False)
    check(not errors and len(lines) == 1, f"a well-formed CHR RAM overflow plans one line: {errors}")
    check(keys == {(A.chr_ram_target(1), A.RESERVED_PALETTE)},
          "the synthetic target key is reported to the caller")
    check(lines[0].endswith(f",{A.chr_ram_target(1)},{A.RESERVED_PALETTE}"),
          "the line's target is the sheet cell's own key, not a restated one")


def check_plan_refusals():
    cases = {
        "cell 9 is not on this sheet": ram_sheet(addition={"cell": 9}),
        "is not marked synthetic": ram_sheet(cell={"synthetic": False}),
        "carries no tile key": ram_sheet(cell={"tiles": []}),
        "not whole pixels": ram_sheet(addition={"offsetX": "left"}),
    }
    for needle, sheet in cases.items():
        _, _, errors = A.plan_sheet_additions([sheet], False)
        check(any(needle in e for e in errors),
              f"plan_sheet_additions refuses a sidecar whose {needle!r}: {errors}")


def check_plan_chr_rom_needs_the_rom():
    cell = {"index": 6, "synthetic": True, "ordinal": 1,
            "tiles": [{"tile": "", "index": 8192, "palette": A.RESERVED_PALETTE}]}
    rec = {"pose": "pose000", "offsetX": 16, "offsetY": -24, "cell": 6,
           "anchor": {"node": 2, "index": 0x412, "tile": "", "palette": "FF0F3919"}}
    sheet = Sheet("usr000", [cell], [rec])
    _, _, errors = A.plan_sheet_additions([sheet], True, 0)
    check(any("--rom" in e for e in errors),
          f"a CHR ROM pack built with no ROM cannot make §3's assertion: {errors}")
    lines, keys, errors = A.plan_sheet_additions([sheet], True, 8192)
    check(not errors and lines and lines[0].startswith("<addition>0412,FF0F3919,16,-24,2000,"),
          f"with the ROM, index 8192 is emitted as 2000 past 8192 CHR tiles: {errors or lines}")
    _, _, errors = A.plan_sheet_additions([sheet], True, 16384)
    check(any("inside the ROM's CHR" in e for e in errors),
          f"a target inside CHR is refused even when the sidecar asked for it: {errors}")


def main():
    check_chr_ram_round_trip()
    check_ordinal_is_one_based()
    check_non_reserved_patterns_rejected()
    check_reserved_palette_evidence()
    check_chr_tile_count()
    check_chr_rom_target()
    check_index_token()
    check_addition_line_round_trip()
    check_target_verdict()
    check_plan_chr_ram()
    check_plan_refusals()
    check_plan_chr_rom_needs_the_rom()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nall mep_addition checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
