#!/usr/bin/env python3
"""Framework-free checks for mep_lint's `<addition>` rules (ADR-0196 §4,
Slice F12.5).

Writes a tiny NES texture pack in a temp dir — one hires.txt, one PNG and one
ADR-0153 sheet sidecar — runs `mep_lint.lint_nes_hires()` on it and asserts on
the exact messages ADR-0196 §4 asks for: an anchor no `<tile>` rule keys, a
target no `<tile>` rule keys, a target the sidecars do not mark synthetic, a
target that fails §3's check for the pack's key kind, `ignorePalette`, a
condition prefix the loader ignores, and a manifest too old for the tag.

Usage: python3 scripts/test_mep_lint_addition.py
"""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import zlib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import mep_addition  # noqa: E402
import mep_lint  # noqa: E402

FAILURES = []

ANCHOR = ("007EFFFFE3E70000007E817E9D18FFFF", "FF36160F")
TARGET = (mep_addition.chr_ram_target(1), mep_addition.RESERVED_PALETTE)


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def tiny_png(width=64, height=64):
    """Minimal valid RGBA PNG (IHDR + one zlib IDAT + IEND)."""
    def chunk(tag, body):
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + b"\x00\x00\x00\xff" * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def pack(lines, sidecar=None, version=109):
    """A folder holding textures/hires.txt with `lines` appended to a minimal
    header, one image, and `sidecar` written as textures/sheets/usr000.json
    when given. Returns the lint report's items."""
    root = Path(tempfile.mkdtemp())
    tex = root / "textures"
    (tex / "sheets").mkdir(parents=True)
    (tex / "usr000.png").write_bytes(tiny_png())
    head = [f"<ver>{version}", "<scale>1", "<supportedRom>" + "0" * 40,
            "<img>usr000.png"]
    (tex / "hires.txt").write_text("\n".join(head + lines) + "\n", encoding="utf-8")
    if sidecar is not None:
        (tex / "sheets" / "usr000.json").write_text(json.dumps(sidecar), encoding="utf-8")
    rep = mep_lint.Report()
    mep_lint.lint_nes_hires(mep_lint.Source(root), "textures/hires.txt", rep)
    return rep.items


def messages(items, level=None):
    return [m for lv, _where, m in items if level is None or lv == level]


def has(items, level, needle):
    return any(needle in m for m in messages(items, level))


def tile(key, x=0, y=0):
    return f"<tile>0,{key[0]},{key[1]},{x},{y},1,N"


def addition(anchor=ANCHOR, offset=(16, -24), target=TARGET, extra="", prefix=""):
    return (f"{prefix}<addition>{anchor[0]},{anchor[1]},{offset[0]},{offset[1]},"
            f"{target[0]},{target[1]}{extra}")


def sidecar(key=TARGET, synthetic=True):
    return {"cells": [{"index": 0, "synthetic": synthetic,
                       "tiles": [{"tile": key[0], "palette": key[1]}]}]}


def check(cond, msg):
    ok(msg) if cond else fail(msg)


# -- the happy path -----------------------------------------------------------

def check_valid_addition():
    items = pack([tile(ANCHOR), tile(TARGET, 8, 0), addition()], sidecar())
    check(not messages(items, "error"),
          f"a well-formed CHR RAM addition lints clean: {messages(items, 'error')}")
    check(has(items, "info", "1 additions"),
          "the info line counts the pack's additions")


# -- ADR-0196 section 4's three refusals ---------------------------------------

def check_anchor_not_keyed():
    items = pack([tile(TARGET, 8, 0), addition()], sidecar())
    check(has(items, "error", "keyed by no <tile> rule in this manifest"),
          "an anchor no <tile> rule keys is an error — the tag can never fire")


def check_target_not_keyed():
    items = pack([tile(ANCHOR), addition()], sidecar())
    check(has(items, "error", "the overflow has no art to draw"),
          "a target no <tile> rule keys is an error")


def check_target_not_marked_synthetic():
    items = pack([tile(ANCHOR), tile(TARGET, 8, 0), addition()],
                 sidecar(synthetic=False))
    check(has(items, "error", "not marked synthetic in any sheet sidecar"),
          "a target the sidecars do not mark synthetic is an error")


def check_no_sidecar_is_a_warning():
    items = pack([tile(ANCHOR), tile(TARGET, 8, 0), addition()])
    check(has(items, "warning", "ships no sheet sidecars"),
          "a pack with no sidecar at all gets a warning, not an error")
    check(not has(items, "error", "not marked synthetic"),
          "and not the marked-synthetic error it cannot check")


# -- ADR-0196 section 3, as the linter can check it ----------------------------

def check_unreserved_palette():
    bad = (TARGET[0], "FF36160F")
    items = pack([tile(ANCHOR), tile(bad, 8, 0), addition(target=bad)], sidecar(bad))
    check(has(items, "error", f"is not the reserved {mep_addition.RESERVED_PALETTE}"),
          "a CHR RAM target whose palette is a recorded one is refused")


def check_unreserved_pattern():
    bad = ("0" * 32, mep_addition.RESERVED_PALETTE)
    items = pack([tile(ANCHOR), tile(bad, 8, 0), addition(target=bad)], sidecar(bad))
    check(has(items, "error", "is not the reserved pattern"),
          "a CHR RAM target that is sixteen zero bytes is refused")


def check_chr_rom_target_inside_chr():
    """On an index-keyed pack the pack-local form of §3 is "past every index
    the manifest itself names"."""
    anchor = ("0412", "FF0F3919")
    good = ("2000", mep_addition.RESERVED_PALETTE)
    inside = ("0100", mep_addition.RESERVED_PALETTE)
    items = pack([tile(anchor), tile(("1FFF", "FF0F3919"), 8, 0), tile(good, 16, 0),
                  addition(anchor=anchor, target=good)], sidecar(good))
    check(not messages(items, "error"),
          f"an index past the pack's own largest keyed index passes: {messages(items, 'error')}")
    items = pack([tile(anchor), tile(("1FFF", "FF0F3919"), 8, 0), tile(inside, 16, 0),
                  addition(anchor=anchor, target=inside)], sidecar(inside))
    check(has(items, "error", "not past the pack's own CHR"),
          "an index the pack itself keys is not provably unmatched")


# -- the tag's own limits ------------------------------------------------------

def check_ignore_palette_refused():
    items = pack([tile(ANCHOR), tile(TARGET, 8, 0), addition(extra=",Y")], sidecar())
    check(has(items, "error", "keeps the palette half of a synthetic key load-bearing"),
          "ignorePalette is refused outright — it is what lets the key collide")


def check_version_floor():
    items = pack([tile(ANCHOR), tile(TARGET, 8, 0), addition()], sidecar(), version=106)
    check(has(items, "error", f"requires <ver>{mep_addition.MIN_VERSION}+"),
          "a manifest older than 107 cannot carry the tag at all")
    items = pack([tile(ANCHOR), tile(TARGET, 8, 0), addition(extra=",N")], sidecar(),
                 version=107)
    check(has(items, "error", f"requires <ver>{mep_addition.IGNORE_PALETTE_VERSION}+"),
          "the seventh field needs 108, even when it is off")


def check_condition_prefix_warns():
    items = pack(["<condition>c1,spriteNearby,0,0,3",
                  tile(ANCHOR), tile(TARGET, 8, 0), addition(prefix="[c1]")], sidecar())
    check(has(items, "warning", "ProcessAdditionTag ignores it"),
          "a condition prefix on <addition> is a warning — the loader drops it")


def check_offscreen_offset_warns():
    items = pack([tile(ANCHOR), tile(TARGET, 8, 0), addition(offset=(400, 0))], sidecar())
    check(has(items, "warning", "is larger than the screen"),
          "an offset that can never land on screen is a warning")


def check_malformed_line():
    items = pack([tile(ANCHOR), tile(TARGET, 8, 0), "<addition>a,b,c"], sidecar())
    check(has(items, "error", "fields"),
          "a line with the wrong field count is one parse error, not a crash")


def main():
    check_valid_addition()
    check_anchor_not_keyed()
    check_target_not_keyed()
    check_target_not_marked_synthetic()
    check_no_sidecar_is_a_warning()
    check_unreserved_palette()
    check_unreserved_pattern()
    check_chr_rom_target_inside_chr()
    check_ignore_palette_refused()
    check_version_floor()
    check_condition_prefix_warns()
    check_offscreen_offset_warns()
    check_malformed_line()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nall addition lint checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
