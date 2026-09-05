#!/usr/bin/env python3
"""Acceptance test for scripts/gameplay_probe.py (PRD F9.13).

Builds synthetic packs on disk — sheet sidecars plus captured
`backgrounds/screenNNN.orig.png` frames — and asserts, clause by clause, that
the "did this recording reach gameplay?" criterion fires where it should and
abstains where it cannot know:

  * `_screen_tiles` recovers the native 256x240 frame from a pack written at
    scale 4 (nearest-neighbour replication), byte-identical to the same frame
    written at scale 1, and rejects a screen whose size is not a whole
    multiple of 256x240;
  * each of the four clauses (A tile structure, B misc share, C screen-area
    churn, D in-screen tile reuse) fires on its own evidence, with its own
    reason string, and clears a pack that is on the good side of it;
  * the clauses that need material abstain without it: churn needs
    MIN_SCREENS_FOR_CHURN captured screens, reuse needs a screen with more
    than MIN_DRAWN_TILES drawn tiles, and a pack with neither a metatiles
    sidecar nor a readable screen is `unknown`, never `gameplay`;
  * the screen series is sampled, not read whole, and `screens` still reports
    the true count;
  * the CLI emits tab-separated fields (a pack path can contain " - ", which
    is why bootstrap_auto_packs.sh cuts on tabs) and `--json` round-trips.

Framework-free, mirroring test_mep_build.py's ok()/fail()/main() style.
Usage: python3 scripts/test_gameplay_probe.py
"""
import json
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gameplay_probe  # noqa: E402

FAILED = 0
PASSED = 0
PROBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gameplay_probe.py")
WIDTH, HEIGHT = 256, 240


def ok(msg):
    global PASSED
    PASSED += 1
    print(f"PASS: {msg}")


def fail(msg):
    global FAILED
    FAILED = 1
    print(f"FAIL: {msg}")


def png_write(path: Path, rows):
    """8-bit RGBA, filter 0 — the same shape as test_sheet_repaint's writer."""
    height, width = len(rows), len(rows[0])
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for px in row:
            raw += bytes(px)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def frame(colour_of, scale=1):
    """A screen built by `colour_of(x, y)`, replicated `scale` times per axis."""
    rows = []
    for y in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            r, g, b = colour_of(x, y)
            row.append((r, g, b, 255))
        rows.extend([[px for px in row for _ in range(scale)]] * scale)
    return rows


def _drawn(x, y, colour):
    """`colour` on a checkerboard, so the 8x8 tile is not one flat colour —
    the probe only counts a tile as drawn when it has more than one colour."""
    return colour if (x + y) % 2 else (0, 0, 0)


def unique_tiles(seed=0):
    """Every 8x8 tile a different colour: a one-off bitmap, reuse == 1.0."""
    return lambda x, y: _drawn(x, y, (((y // 8) * 32 + x // 8) % 256, (y // 8) // 8, seed + 90))


def tiled(seed=0, palette=6):
    """A small tile set repeated across the screen: reuse == 960 / palette."""
    return lambda x, y: _drawn(x, y, (10 + ((x // 8 + y // 8 + seed) % palette) * 20, 60, 120))


def blank_but(count):
    """A flat screen with only `count` drawn tiles (the rest one flat colour)."""
    return lambda x, y: ((7, 7, 7) if (y // 8) * 32 + x // 8 >= count
                         else _drawn(x, y, (200, x // 8, y // 8)))


def write_pack(root, sheets=None, screens=(), scale=1, name="Game"):
    """A pack folder: <name>/auto/textures/{sheets,backgrounds}."""
    textures = Path(root) / name / "auto" / "textures"
    sheet_dir = textures / "sheets"
    sheet_dir.mkdir(parents=True, exist_ok=True)
    for filename, doc in (sheets or {}).items():
        (sheet_dir / filename).write_text(json.dumps(doc))
    for index, colour_of in enumerate(screens):
        png_write(textures / "backgrounds" / ("screen%03d.orig.png" % index),
                  frame(colour_of, scale))
    return str(sheet_dir)


def metatiles(alt8x8=0.97, cells=40):
    return {"version": 1, "kind": "metatiles", "gridUnit": 16,
            "gridPhase": {"x": 0, "y": 0},
            "gridConsistency": {"chosen": alt8x8, "alt8x8": alt8x8},
            "cells": [{"index": i} for i in range(cells)]}


def misc_sheet(cells):
    return {"version": 1, "kind": "misc", "cells": [{"index": i} for i in range(cells)]}


def verdict_of(sheet_dir):
    return gameplay_probe.probe(sheet_dir)


def screen_tiles(sheet_dir, index=0):
    """`_screen_tiles` on a pack's screen; an exception is a failed assertion,
    not a crashed suite - the probe must survive whatever is on disk."""
    path = os.path.join(os.path.dirname(sheet_dir), "backgrounds",
                        "screen%03d.orig.png" % index)
    try:
        return gameplay_probe._screen_tiles(path)
    except Exception as exc:  # noqa: BLE001 - reported as a failure below
        return exc


def test_screen_tiles_downsamples(root):
    at1 = write_pack(root, screens=[tiled()], scale=1, name="Scale1")
    at4 = write_pack(root, screens=[tiled()], scale=4, name="Scale4")
    a, b = screen_tiles(at1), screen_tiles(at4)
    if isinstance(a, Exception) or isinstance(b, Exception):
        fail(f"_screen_tiles decodes a captured screen without raising ({a!r} {b!r})")
        return
    if a is None or len(a) != 960 or len(a[0]) != 8 * 8 * 3:
        fail(f"_screen_tiles returns 960 tiles of 8x8 RGB (got {a and len(a)})")
        return
    if a != b:
        fail("_screen_tiles recovers the same native frame from a 4x pack")
        return
    ok("_screen_tiles recovers the native 256x240 frame at scale 1 and scale 4 alike")


def test_screen_tiles_rejects_odd_size(root):
    path = Path(root) / "Odd" / "auto" / "textures" / "backgrounds" / "screen000.orig.png"
    png_write(path, [[(0, 0, 0, 255)] * 300] * 200)
    got = screen_tiles(str(Path(root) / "Odd" / "auto" / "textures" / "sheets"))
    if got is not None:
        fail(f"_screen_tiles rejects a screen that is not a multiple of 256x240 (got {got!r})")
        return
    ok("_screen_tiles rejects a screen that is not a whole multiple of 256x240")


def test_clause_a_tile_structure(root):
    stuck = verdict_of(write_pack(root, sheets={"metatiles.json": metatiles(0.76)},
                                  screens=[tiled()], name="StructBad"))
    good = verdict_of(write_pack(root, sheets={"metatiles.json": metatiles(0.97)},
                                 screens=[tiled()], name="StructOk"))
    if stuck["verdict"] != "menu-only" or not any(
            "no repeating tile structure" in r for r in stuck["reasons"]):
        fail(f"clause A flags a low gridConsistency.alt8x8 (got {stuck})")
        return
    if good["verdict"] != "gameplay":
        fail(f"clause A clears a high gridConsistency.alt8x8 (got {good})")
        return
    ok("clause A: alt8x8 below MIN_TILE_STRUCTURE is menu-only, above it is not")


def test_clause_b_misc_share(root):
    noisy = verdict_of(write_pack(
        root, sheets={"metatiles.json": metatiles(), "misc.json": misc_sheet(40)},
        screens=[tiled()], name="MiscBad"))
    clean = verdict_of(write_pack(
        root, sheets={"metatiles.json": metatiles(), "misc.json": misc_sheet(4)},
        screens=[tiled()], name="MiscOk"))
    if noisy["verdict"] != "menu-only" or not any(
            "off-grid noise" in r for r in noisy["reasons"]):
        fail(f"clause B flags a vocabulary that is mostly misc (got {noisy})")
        return
    if clean["verdict"] != "gameplay":
        fail(f"clause B clears a small misc share (got {clean})")
        return
    ok("clause B: a misc-dominated vocabulary is menu-only, a small misc share is not")


def test_clause_c_churn(root):
    # Six screens where only the top two rows ever differ: a text field being
    # typed into, the shape of a name/password entry screen.
    def field(step):
        return lambda x, y: (tiled()(x, y) if y >= 16
                             else _drawn(x, y, (step * 7 + x // 8 + 1, 30, 30)))
    stuck = verdict_of(write_pack(root, sheets={"metatiles.json": metatiles()},
                                  screens=[field(i) for i in range(6)], name="ChurnBad"))
    moving = verdict_of(write_pack(root, sheets={"metatiles.json": metatiles()},
                                   screens=[tiled(i) for i in range(6)], name="ChurnOk"))
    if stuck["verdict"] != "menu-only" or not any(
            "ever changes" in r for r in stuck["reasons"]):
        fail(f"clause C flags a screen series where almost nothing moves (got {stuck})")
        return
    if stuck["metrics"]["screens"] != 6:
        fail(f"the reason reports the real screen count (got {stuck['metrics']})")
        return
    if moving["verdict"] != "gameplay":
        fail(f"clause C clears a series where the whole screen moves (got {moving})")
        return
    ok("clause C: a series that only rewrites a text field is menu-only, a scrolling one is not")


def test_clause_c_abstains_without_a_series(root):
    result = verdict_of(write_pack(root, sheets={"metatiles.json": metatiles()},
                                   screens=[tiled(), tiled()], name="ChurnShort"))
    if result["metrics"]["everChanged"] is not None:
        fail(f"churn abstains below MIN_SCREENS_FOR_CHURN screens (got {result['metrics']})")
        return
    if result["verdict"] != "gameplay":
        fail(f"a two-screen pack is not condemned by churn (got {result})")
        return
    ok("clause C abstains below MIN_SCREENS_FOR_CHURN captured screens")


def test_clause_d_tile_reuse(root):
    oneoff = verdict_of(write_pack(root, sheets={"metatiles.json": metatiles()},
                                   screens=[unique_tiles()], name="ReuseBad"))
    playfield = verdict_of(write_pack(root, sheets={"metatiles.json": metatiles()},
                                      screens=[tiled()], name="ReuseOk"))
    if oneoff["verdict"] != "menu-only" or not any(
            "one-off bitmaps" in r for r in oneoff["reasons"]):
        fail(f"clause D flags a screen whose tiles are all unique (got {oneoff})")
        return
    if playfield["verdict"] != "gameplay":
        fail(f"clause D clears a screen built from a repeated tile set (got {playfield})")
        return
    ok("clause D: an all-unique screen is menu-only, a repeated tile set is not")


def test_clause_d_takes_the_best_screen(root):
    # One real playfield screen among title cards is enough to clear the pack.
    mixed = verdict_of(write_pack(
        root, sheets={"metatiles.json": metatiles()},
        screens=[unique_tiles(1), unique_tiles(2), tiled()], name="ReuseMixed"))
    if mixed["verdict"] != "gameplay":
        fail(f"reuse is the maximum over screens, not the mean (got {mixed})")
        return
    ok("clause D takes the best screen: one gameplay screen clears a pack of title cards")


def test_reuse_abstains_on_a_near_blank_screen(root):
    result = verdict_of(write_pack(
        root, sheets={"metatiles.json": metatiles()},
        screens=[blank_but(gameplay_probe.MIN_DRAWN_TILES - 1)], name="Fade"))
    if result["metrics"]["reuse"] is not None:
        fail(f"a near-blank screen gets no vote (got {result['metrics']})")
        return
    if result["verdict"] != "gameplay":
        fail(f"a near-blank screen alone is not menu-only (got {result})")
        return
    ok("clause D abstains on a screen with fewer than MIN_DRAWN_TILES drawn tiles")


def test_unknown_when_nothing_is_measurable(root):
    result = verdict_of(write_pack(root, sheets={"font.json": {"version": 1, "kind": "font",
                                                               "cells": [{"index": 0}]}},
                                   screens=[], name="Empty"))
    if result["verdict"] != "unknown":
        fail(f"a pack with no metatiles sidecar and no screens is unknown (got {result})")
        return
    ok("a pack with neither a metatiles sidecar nor a readable screen is `unknown`")


def test_screens_are_sampled(root):
    # 51 and 24 are spelled out on purpose: a test that reads the cap out of
    # the module under test cannot notice the cap being raised.
    total, cap = 51, 24
    sheet_dir = write_pack(root, sheets={"metatiles.json": metatiles()},
                           screens=[tiled(i) for i in range(total)], name="Many")
    seen = []
    original = gameplay_probe._screen_tiles

    def counting(path):
        seen.append(path)
        return original(path)

    gameplay_probe._screen_tiles = counting
    try:
        result = verdict_of(sheet_dir)
    finally:
        gameplay_probe._screen_tiles = original
    if len(seen) > cap or len(seen) > gameplay_probe.MAX_SCREENS_SAMPLED:
        fail(f"at most {cap} screens are decoded out of {total} (decoded {len(seen)})")
        return
    if len(set(seen)) != len(seen):
        fail("the sampled screens are distinct")
        return
    if result["metrics"]["screens"] != total:
        fail(f"`screens` reports the true count, not the sample (got {result['metrics']})")
        return
    ok(f"at most {cap} screens are decoded out of {total}, "
       "while `screens` still reports the true count")


def test_cli_is_tab_separated(root):
    # A pack name containing " - " is why the CLI cannot use " - " as its
    # separator: bootstrap_auto_packs.sh cuts these fields on tabs.
    name = "The Flintstones - The Surprise at Dinosaur Peak!"
    write_pack(root, sheets={"metatiles.json": metatiles(0.5)},
               screens=[unique_tiles()], name=name)
    proc = subprocess.run([sys.executable, PROBE, root], capture_output=True, text=True)
    if proc.returncode != 0:
        fail(f"the CLI exits 0 on a readable library (rc={proc.returncode}, {proc.stderr})")
        return
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    row = next((ln for ln in lines if name in ln), None)
    if row is None:
        fail(f"the CLI reports the pack (got {lines})")
        return
    fields = row.split("\t")
    if len(fields) != 3 or fields[0] != "menu-only" or name not in fields[1]:
        fail(f"the CLI emits verdict/path/reasons as three tab-separated fields (got {fields!r})")
        return
    if " - " not in fields[1] or not fields[2]:
        fail(f"the path keeps its ' - ' and the reason is not empty (got {fields!r})")
        return
    ok("the CLI emits three tab-separated fields, so a ' - ' in the pack path cannot forge one")


def test_cli_json(root):
    proc = subprocess.run([sys.executable, PROBE, root, "--json"],
                          capture_output=True, text=True)
    try:
        docs = json.loads(proc.stdout)
    except ValueError:
        fail(f"--json emits parseable JSON (got {proc.stdout[:120]!r})")
        return
    if not docs or not all({"verdict", "reasons", "metrics", "path"} <= set(d) for d in docs):
        fail(f"--json carries verdict, reasons, metrics and path per pack (got {docs})")
        return
    ok("--json emits one object per pack with verdict, reasons, metrics and path")


def test_no_argument_is_an_error():
    proc = subprocess.run([sys.executable, PROBE], capture_output=True, text=True)
    if proc.returncode != 2 or "Usage" not in proc.stderr:
        fail(f"a bare invocation prints usage and exits 2 (rc={proc.returncode})")
        return
    ok("a bare invocation prints the usage line and exits 2")


def test_sheet_report_wiring(root):
    report = os.path.join(os.path.dirname(PROBE), "sheet_report.py")
    write_pack(root, sheets={"metatiles.json": metatiles(0.5)},
               screens=[unique_tiles()], name="Wired")
    proc = subprocess.run([sys.executable, report, root, "--fail-menu-only"],
                          capture_output=True, text=True)
    if "gameplay  : menu-only" not in proc.stdout:
        fail(f"sheet_report.py prints the gameplay verdict (got {proc.stdout[:400]!r})")
        return
    if proc.returncode == 0:
        fail("sheet_report.py --fail-menu-only exits non-zero on a menu-only pack")
        return
    ok("sheet_report.py prints the verdict and --fail-menu-only exits non-zero on a menu-only pack")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        test_screen_tiles_downsamples(tmp)
        test_screen_tiles_rejects_odd_size(tmp)
        test_clause_a_tile_structure(tmp)
        test_clause_b_misc_share(tmp)
        test_clause_c_churn(tmp)
        test_clause_c_abstains_without_a_series(tmp)
        test_clause_d_tile_reuse(tmp)
        test_clause_d_takes_the_best_screen(tmp)
        test_reuse_abstains_on_a_near_blank_screen(tmp)
        test_unknown_when_nothing_is_measurable(tmp)
        test_screens_are_sampled(tmp)
        test_no_argument_is_an_error()
    with tempfile.TemporaryDirectory() as tmp:
        test_cli_is_tab_separated(tmp)
        test_cli_json(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        test_sheet_report_wiring(tmp)
    print(f"{PASSED} check(s) passed, {'some failed' if FAILED else 'none failed'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
