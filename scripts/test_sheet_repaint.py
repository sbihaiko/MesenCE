#!/usr/bin/env python3
"""Acceptance test for scripts/sheet_repaint.py (PRD F9.6, ADR-0154).

Builds a synthetic ADR-0153 sheet folder — a 4-cell metatile vocabulary with
one palette variant and one transparent hole, plus a 2-cell stitched map —
and asserts the parts of the repaint pipeline that do not depend on the model:

  * the `passthrough` backend round-trips the sheet unchanged in structure:
    at scale 1 with no seam pass the output is byte-identical to the input,
    at scale 4 it is exactly the nearest-neighbour upscale, and the sidecar
    plus the `*.orig.png` twin come across untouched;
  * the seam pass writes **only** the border band of cells that are adjacent
    in game (adjacency read off the map's `placements[]`), leaving every
    interior pixel and every gutter pixel alone, and it produces the plain
    average of the two touching lines at the border;
  * alpha survives: the gutter and the in-cell hole stay fully transparent,
    the RGB of a transparent pixel is zeroed, and no opaque pixel is lost;
  * a palette variant is rebuilt from the canonical generation and lands on
    its own colours, keeping the canonical silhouette;
  * `pack.json` carries the ADR-0154 §3 `generated` object, with `targets`
    inherited from the neighbouring manifest, and the whole output survives
    `mep_build.py build` (which lints it).

Framework-free, mirroring test_mep_build.py's ok()/fail()/main() style.
Usage: python3 scripts/test_sheet_repaint.py
"""

import http.server
import json
import os
import struct
import subprocess
import sys
import tempfile
import threading
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPAINT = REPO / "scripts" / "sheet_repaint.py"
MEP_BUILD = REPO / "scripts" / "mep_build.py"
PY = sys.executable

FAILED = 0
PASSED = 0

UNIT = 16
GUTTER = 1
COLUMNS = 3
STRIDE = UNIT + GUTTER
TRANSPARENT = (0, 0, 0, 0)
# The fixture paints its transparent pixels magenta-under-zero-alpha: a real
# PNG editor leaves colour under a transparent pixel, and ADR-0154 §7 requires
# the repaint to zero it so no halo can leak into a sliced crop. Painting them
# black would make that assertion vacuous.
GHOST = (255, 0, 255, 0)
ROM_SHA1 = "2A4E126D0286BEA0BF503C80A12352C57539F76B"
PAL_A = "0F162A30"
PAL_B = "0F1626307"[:8]

# Two flat colours per cell, chosen so the frequency ordering read by
# _palette_of is unambiguous: the major colour covers 12 of the 16 columns.
CELL_COLOURS = {
    0: ((200, 40, 40), (40, 200, 40)),      # canonical of shape A
    1: ((10, 10, 10), (250, 250, 250)),     # shape B, the map's east neighbour
    2: ((60, 60, 220), (220, 220, 40)),     # shape A again, other palette
    3: ((90, 140, 90), (140, 90, 140)),     # shape C
}
# Cell 2 is the palette variant of cell 0: same shape tuple, different palette.
CELL_SHAPE = {0: "A", 1: "B", 2: "A", 3: "C"}
CELL_PALETTE = {0: PAL_A, 1: PAL_A, 2: PAL_B, 3: PAL_A}
CELL_COUNT = {0: 100, 1: 80, 2: 20, 3: 5}
HOLE = (2, 2, 4, 4)  # x0, y0, x1, y1 inside a cell — the alpha test
# Cell 2's hole sits somewhere else on purpose: the variant is rebuilt from
# cell 0's generation, so its output must carry cell 0's hole, not its own.
# Without that difference the recolour test would also pass if the whole
# variant path never ran.
HOLE_BY_CELL = {2: (10, 2, 12, 4)}


def ok(msg):
    global PASSED
    PASSED += 1
    print(f"PASS: {msg}")


def fail(msg):
    global FAILED
    FAILED = 1
    print(f"FAIL: {msg}")


# --- tiny PNG codec (filter 0, 8-bit RGBA), same shape as test_mep_build's ---


def png_write(path: Path, rows):
    height, width = len(rows), len(rows[0])
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for px in row:
            raw += bytes(px)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def png_read(path: Path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    pos, idat, width, height = 8, b"", 0, 0
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            width, height, depth, color = struct.unpack(">IIBB", body[:10])
            assert (depth, color) == (8, 6), (depth, color)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = width * 4
    rows = []
    for y in range(height):
        off = y * (stride + 1)
        assert raw[off] == 0, "test PNGs are written with filter 0 only"
        line = raw[off + 1:off + 1 + stride]
        rows.append([tuple(line[i:i + 4]) for i in range(0, stride, 4)])
    return rows


def upscale(rows, n):
    return [[px for px in row for _ in range(n)] for row in rows for _ in range(n)]


def blank(width, height):
    return [[GHOST] * width for _ in range(height)]


def normalize(rows):
    """The one thing passthrough does change: ADR-0154 §7 zeroes the RGB of a
    fully transparent pixel. Identity is asserted against that."""
    return [[TRANSPARENT if px[3] == 0 else px for px in row] for row in rows]


# --- fixture ----------------------------------------------------------------


def tile_hex(shape: str, k: int) -> str:
    """A distinct 32-hex tile key per (shape, position in the metatile)."""
    seed = (ord(shape) * 16 + k) & 0xFF
    return bytes((seed + i) & 0xFF for i in range(16)).hex().upper()


def paint_cell(rows, x, y, colours, hole=HOLE):
    major, minor = colours
    for row in range(UNIT):
        for col in range(UNIT):
            rows[y + row][x + col] = (major if col < 12 else minor) + (255,)
    for row in range(hole[1], hole[3]):
        for col in range(hole[0], hole[2]):
            rows[y + row][x + col] = GHOST


def cell_origin(index):
    return GUTTER + (index % COLUMNS) * STRIDE, GUTTER + (index // COLUMNS) * STRIDE


def make_fixture(root: Path):
    """<Game>/auto/textures/sheets with metatiles + map, plus the recorder's
    hires.txt key source and a neighbouring mep/pack.json to inherit from."""
    game = root / "Game"
    sheets = game / "auto" / "textures" / "sheets"
    sheets.mkdir(parents=True)

    rows_count = (len(CELL_COLOURS) + COLUMNS - 1) // COLUMNS
    width = COLUMNS * STRIDE + GUTTER
    height = rows_count * STRIDE + GUTTER
    pixels = blank(width, height)
    cells = []
    for index in sorted(CELL_COLOURS):
        x, y = cell_origin(index)
        paint_cell(pixels, x, y, CELL_COLOURS[index], HOLE_BY_CELL.get(index, HOLE))
        shape = CELL_SHAPE[index]
        cells.append({
            "index": index, "x": x, "y": y, "count": CELL_COUNT[index],
            "context": "scene", "metatile": index, "label": "",
            "tiles": [{"tile": tile_hex(shape, k), "palette": CELL_PALETTE[index]} for k in range(4)],
        })
    png_write(sheets / "metatiles.png", pixels)
    png_write(sheets / "metatiles.orig.png", pixels)
    (sheets / "metatiles.json").write_text(json.dumps({
        "version": 1, "kind": "metatiles", "gridUnit": UNIT,
        "gridPhase": {"x": 0, "y": 0}, "hasGrid": True, "phaseAdvantage": 0.34,
        "cell": {"w": UNIT, "h": UNIT}, "gutter": GUTTER, "columns": COLUMNS,
        "sheet": "metatiles.png", "reference": "metatiles.orig.png", "cells": cells,
    }, indent=2), encoding="utf-8")

    # A 2x1 map over vocabulary cells 0 and 1: this is where the adjacency
    # pair (0, "E", 1) comes from, and it is applied back on metatiles.png.
    placements = [{"x": 0, "y": 0, "cell": 0}, {"x": UNIT, "y": 0, "cell": 1}]
    map_pixels = blank(UNIT * 2, UNIT)
    paint_cell(map_pixels, 0, 0, CELL_COLOURS[0])
    paint_cell(map_pixels, UNIT, 0, CELL_COLOURS[1])
    png_write(sheets / "map-000.png", map_pixels)
    png_write(sheets / "map-000.orig.png", map_pixels)
    (sheets / "map-000.json").write_text(json.dumps({
        "version": 1, "kind": "map", "gridUnit": UNIT,
        "gridPhase": {"x": 0, "y": 0}, "cell": {"w": UNIT, "h": UNIT},
        "gutter": 0, "columns": 1, "sheet": "map-000.png",
        "reference": "map-000.orig.png", "mode": "screen", "hudRows": 0,
        "placements": placements, "cells": [],
    }, indent=2), encoding="utf-8")

    lines = ["<ver>107", "<scale>1", "<system>nes", f"<supportedRom>{ROM_SHA1}", "<img>old.png"]
    for index in sorted(CELL_COLOURS):
        for k in range(4):
            lines.append(f"<tile>0,{tile_hex(CELL_SHAPE[index], k)},{CELL_PALETTE[index]},0,0,1,N")
    (game / "auto" / "textures" / "hires.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    mep = game / "mep"
    mep.mkdir()
    (mep / "pack.json").write_text(json.dumps({
        "mep": "1.5.0", "name": "Game — artist pack", "version": "1.0.0",
        "id": "game-artist-pack", "license": "CC0-1.0",
        "targets": [{"system": "nes", "sha1": ROM_SHA1}],
        "sections": {"textures": {"path": "textures/"}},
    }, indent=2), encoding="utf-8")
    return game, sheets


def run_repaint(target, out, *extra, expect=0):
    cmd = [PY, str(REPAINT), str(target), "--out", str(out), *extra]
    # A developer's SHEET_REPAINT_* environment (a real ComfyUI endpoint, a
    # local Real-ESRGAN) must not decide what these assertions see.
    env = {k: v for k, v in os.environ.items() if not k.startswith("SHEET_REPAINT_")}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != expect:
        fail(f"sheet_repaint {' '.join(extra)} -> exit {proc.returncode}, expected {expect}\n"
             f"{proc.stdout}{proc.stderr}")
        return None
    return proc.stdout + proc.stderr


# --- the tests --------------------------------------------------------------


def test_passthrough_structure(root: Path, sheets: Path):
    """The whole point of the passthrough backend: nothing but the resolution
    changes, so the rest of the pipeline can be tested without a model."""
    out = root / "out-identity"
    if run_repaint(sheets, out, "--scale", "1", "--seam-width", "0", "--no-variants") is None:
        return
    got_dir = out / "textures" / "sheets"
    for name in ("metatiles.png", "map-000.png"):
        if png_read(got_dir / name) != normalize(png_read(sheets / name)):
            fail(f"passthrough at scale 1 changed {name}")
            return
    for name in ("metatiles.json", "map-000.json", "metatiles.orig.png", "map-000.orig.png"):
        if (got_dir / name).read_bytes() != (sheets / name).read_bytes():
            fail(f"{name} was not carried across verbatim")
            return
    ok("passthrough at scale 1 round-trips every sheet unchanged, sidecar and twin verbatim")

    out4 = root / "out-scale4"
    if run_repaint(sheets, out4, "--scale", "4", "--seam-width", "0", "--no-variants") is None:
        return
    got = png_read(out4 / "textures" / "sheets" / "metatiles.png")
    want = upscale(normalize(png_read(sheets / "metatiles.png")), 4)
    if got != want:
        fail("passthrough at scale 4 is not the exact nearest-neighbour upscale")
        return
    ok("passthrough at scale 4 is exactly the nearest-neighbour upscale (structure preserved)")


def test_seam_pass_touches_only_borders(root: Path, sheets: Path):
    """ADR-0154 §6: the pass writes the border band of adjacent cells and
    nothing else — not the interior, not the gutter."""
    base = root / "out-noseam"
    seamed = root / "out-seam"
    if run_repaint(sheets, base, "--scale", "1", "--seam-width", "0", "--no-variants") is None:
        return
    if run_repaint(sheets, seamed, "--scale", "1", "--seam-width", "1", "--no-variants") is None:
        return

    before = png_read(base / "textures" / "sheets" / "metatiles.png")
    after = png_read(seamed / "textures" / "sheets" / "metatiles.png")
    changed = [(x, y) for y in range(len(before)) for x in range(len(before[0]))
               if before[y][x] != after[y][x]]
    if not changed:
        fail("the seam pass changed nothing on metatiles.png (adjacency (0,E,1) was not applied)")
        return

    x0, y0 = cell_origin(0)
    x1, y1 = cell_origin(1)
    allowed = {(x0 + UNIT - 1, y0 + k) for k in range(UNIT)} | {(x1, y1 + k) for k in range(UNIT)}
    stray = [c for c in changed if c not in allowed]
    if stray:
        fail(f"the seam pass wrote {len(stray)} pixel(s) outside the border band, e.g. {stray[:3]}")
        return
    ok("the seam pass writes only the border band of the adjacent cells (no interior, no gutter)")

    # The border itself is the plain average of the two touching lines.
    want = tuple(round((a + b) / 2) for a, b in zip(CELL_COLOURS[0][1], CELL_COLOURS[1][0])) + (255,)
    got_a = after[y0][x0 + UNIT - 1]
    got_b = after[y1][x1]
    if got_a != want or got_b != want:
        fail(f"border lines are {got_a}/{got_b}, expected the average {want} on both sides")
        return
    ok("both sides of a seam become the same average, so a stripe crosses the border continuously")

    # The same pass on the map, where the two cells really are adjacent.
    map_after = png_read(seamed / "textures" / "sheets" / "map-000.png")
    if map_after[0][UNIT - 1] != want or map_after[0][UNIT] != want:
        fail("the map's geometric seam was not symmetrised")
        return
    ok("the map's geometric neighbours are symmetrised the same way")


def test_alpha_survives(root: Path, sheets: Path):
    """ADR-0154 §7: alpha comes from the source, transparent stays transparent
    and its RGB is zeroed so no halo leaks into a sliced crop."""
    # --no-variants, so this compares the sheet against itself cell by cell:
    # the variant path deliberately replaces cell 2 with cell 0's silhouette,
    # which is the subject of test_palette_variant_recolour, not of this one.
    out = root / "out-alpha"
    if run_repaint(sheets, out, "--scale", "2", "--no-variants") is None:
        return
    got = png_read(out / "textures" / "sheets" / "metatiles.png")
    src = png_read(sheets / "metatiles.png")

    lost = [(x, y) for y in range(len(src)) for x in range(len(src[0]))
            if (src[y][x][3] == 0) != (got[y * 2][x * 2][3] == 0)]
    if lost:
        fail(f"{len(lost)} pixel(s) changed transparency, e.g. {lost[:3]}")
        return
    ok("every transparent pixel stays transparent and every opaque one stays opaque")

    x0, y0 = cell_origin(0)
    hole = got[(y0 + HOLE[1]) * 2][(x0 + HOLE[0]) * 2]
    gutter = got[0][0]
    if hole != TRANSPARENT or gutter != TRANSPARENT:
        fail(f"transparent RGB was not zeroed, so a crop can carry a halo "
             f"(hole {hole}, gutter {gutter}, source paints them {GHOST})")
        return
    ok("the in-cell hole and the gutter keep alpha 0 with zeroed RGB (no halo into a crop)")


def test_palette_variant_recolour(root: Path, sheets: Path):
    """ADR-0154 §5: cell 2 is cell 0's shape under another palette, so it is
    rebuilt from cell 0's single generation — same silhouette, own colours."""
    out = root / "out-variants"
    if run_repaint(sheets, out, "--scale", "1") is None:
        return
    got = png_read(out / "textures" / "sheets" / "metatiles.png")
    src = png_read(sheets / "metatiles.png")
    x2, y2 = cell_origin(2)
    x0, y0 = cell_origin(0)

    # Expected: cell 0's geometry (including *its* hole) under cell 2's colours.
    swap = dict(zip(CELL_COLOURS[0], CELL_COLOURS[2]))
    want = [[(swap[src[y0 + cy][x0 + cx][:3]] + (255,)) if src[y0 + cy][x0 + cx][3] else TRANSPARENT
             for cx in range(UNIT)] for cy in range(UNIT)]
    have = [[got[y2 + cy][x2 + cx] for cx in range(UNIT)] for cy in range(UNIT)]
    if have != want:
        first = next((cx, cy) for cy in range(UNIT) for cx in range(UNIT)
                     if have[cy][cx] != want[cy][cx])
        fail(f"the recoloured variant is wrong at {first}: got {have[first[1]][first[0]]}, "
             f"want {want[first[1]][first[0]]}")
        return
    if have == [[normalize([src[y2 + cy]])[0][x2 + cx] for cx in range(UNIT)] for cy in range(UNIT)]:
        fail("the variant cell is just its own source — the recolour path never ran")
        return
    ok("a palette variant is rebuilt from the canonical generation and lands on its own colours")

    silhouette_a = [got[y0 + cy][x0 + cx][3] for cy in range(UNIT) for cx in range(UNIT)]
    silhouette_b = [got[y2 + cy][x2 + cx][3] for cy in range(UNIT) for cx in range(UNIT)]
    if silhouette_a != silhouette_b:
        fail("the variant's silhouette differs from the canonical one")
        return
    ok("the variant keeps the canonical silhouette (one generation, one alpha mask)")


def test_pack_json_label(root: Path, sheets: Path):
    out = root / "out-label"
    if run_repaint(sheets, out, "--scale", "2", "--backend", "null") is None:
        return
    doc = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    gen = doc.get("generated")
    if not isinstance(gen, dict) or gen.get("by") != "sheet_repaint":
        fail(f"pack.json carries no ADR-0154 'generated' object: {doc}")
        return
    if gen.get("backend") != "passthrough" or gen.get("scale") != 2:
        fail(f"'generated' does not record the run: {gen}")
        return
    ok("pack.json carries the ADR-0154 §3 'generated' object naming the backend and the scale")

    if doc.get("targets") != [{"system": "nes", "sha1": ROM_SHA1}]:
        fail(f"'targets' was not inherited from the neighbouring manifest: {doc.get('targets')}")
        return
    ok("'targets' is inherited from the neighbouring pack.json, never invented")


def test_survives_mep_build(root: Path, sheets: Path):
    """PRD F9.4/F9.6: the repaint has to go back through mep_build (which
    lints it) and come out as hires.txt entries pointing at the new sheets."""
    out = root / "out-build"
    if run_repaint(sheets, out, "--scale", "2") is None:
        return
    proc = subprocess.run(
        [PY, str(MEP_BUILD), "build", str(out), "--source", str(sheets.parent / "hires.txt")],
        capture_output=True, text=True)
    if proc.returncode != 0:
        fail(f"mep_build build on the repaint -> exit {proc.returncode}\n{proc.stdout}{proc.stderr}")
        return
    manifest = (out / "textures" / "hires.txt").read_text(encoding="utf-8")
    if "metatiles.png" not in manifest or "<tile>" not in manifest:
        fail("mep_build produced no tile entries pointing at the repainted sheets")
        return
    ok("the repaint survives mep_build build: it lints clean and slices back into hires.txt")


def test_no_sheets_is_an_error(root: Path):
    empty = root / "empty"
    (empty / "textures" / "sheets").mkdir(parents=True)
    proc = subprocess.run([PY, str(REPAINT), str(empty)], capture_output=True, text=True)
    if proc.returncode != 1 or "no sheets" not in (proc.stdout + proc.stderr):
        fail(f"an empty sheets folder -> exit {proc.returncode}, expected 1 with a message")
        return
    ok("a folder with no ADR-0153 sidecar exits 1 with a message instead of crashing")

# --- fixtures for the new paths ---------------------------------------------

# 3x3 staircase: the smallest picture on which Scale2x provably differs from a
# nearest-neighbour upscale. Hand-derived below, in test_classical_backend.
BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
STAIR = [[BLACK, BLACK, BLACK],
         [BLACK, BLACK, WHITE],
         [BLACK, WHITE, WHITE]]


def make_stair_fixture(root: Path):
    """A one-sheet folder with no cells: no palette variants, no adjacency,
    nothing but the scaler under test."""
    sheets = root / "Stair" / "sheets"
    sheets.mkdir(parents=True)
    png_write(sheets / "stair.png", STAIR)
    png_write(sheets / "stair.orig.png", STAIR)
    (sheets / "stair.json").write_text(json.dumps({
        "version": 1, "kind": "misc", "gridUnit": 8, "cell": {"w": 8, "h": 8},
        "gutter": 0, "columns": 1, "sheet": "stair.png",
        "reference": "stair.orig.png", "cells": [],
    }, indent=2), encoding="utf-8")
    return sheets


SCREEN_PIXELS = [[(10 * x, 20 * y, 30, 255) for x in range(8)] for y in range(6)]
SCREEN_LINE = "[screen001_A&screen001_B]<background>backgrounds/screen001.png,1,0,0,20"
SCREEN_SCALE = 2


def make_screens_fixture(root: Path):
    """<Game>/auto/textures with the recorder's hires.txt: two condition-
    prefixed <background> entries (one of which names a file that is not
    there), one condition nothing references, and the <img>/<tile> layer the
    repaint must NOT copy into its own manifest."""
    textures = root / "ScreenGame" / "auto" / "textures"
    (textures / "backgrounds").mkdir(parents=True)
    png_write(textures / "backgrounds" / "screen001.png", SCREEN_PIXELS)
    png_write(textures / "backgrounds" / "screen001.orig.png", SCREEN_PIXELS)
    png_write(textures / "Chr_00_0.png", SCREEN_PIXELS)
    (textures / "hires.txt").write_text("\n".join([
        "<ver>107",
        f"<scale>{SCREEN_SCALE}",
        "<system>nes",
        f"<supportedRom>{ROM_SHA1}",
        "<overscan>0,0,0,0",
        "<condition>screen001_A,tileAtPosition,168,104,1F1E,0F20210F",
        "<condition>screen001_B,tileAtPosition,112,136,1F0F,0F20210F",
        "<condition>unused_C,tileAtPosition,8,8,0000,0F20210F",
        "<img>Chr_00_0.png",
        f"<tile>0,{tile_hex('A', 0)},{PAL_A},0,0,1,N",
        SCREEN_LINE,
        "[screen002_A]<background>backgrounds/screen002.png,1,0,0,20",
    ]) + "\n", encoding="utf-8")
    return textures


# --- the classical (non-generative) baseline --------------------------------


def test_classical_backend(root: Path, sheets: Path):
    """ADR-0154 §2's baseline arm. Scale2x is a *copy-only* scaler: it rounds
    a staircase corner without inventing a colour, which is what makes it a
    fair B in the blind A/B and what keeps alpha and palette out of the
    comparison."""
    stair = make_stair_fixture(root)
    out = root / "out-classical-stair"
    if run_repaint(stair, out, "--scale", "2", "--seam-width", "0", "--backend", "classical") is None:
        return
    got = png_read(out / "sheets" / "stair.png") if (out / "sheets").is_dir() else \
        png_read(out / "textures" / "sheets" / "stair.png")
    if len(got) != 6 or len(got[0]) != 6:
        fail(f"classical at scale 2 produced {len(got[0])}x{len(got)}, expected 6x6")
        return
    # Centre pixel E=(1,1)=black, with B=black above, D=black left, F=white
    # right, H=white below. B != H and D != F, so Scale2x fires:
    #   E0 = D (D==B) = black, E1 = E (B!=F) = black,
    #   E2 = E (D!=H) = black, E3 = F (H==F) = WHITE.
    # A nearest-neighbour upscale puts black in all four.
    if got[3][3] != WHITE:
        fail(f"classical did not round the staircase corner: (3,3) is {got[3][3]}, expected white "
             "— that pixel is exactly where Scale2x differs from nearest neighbour")
        return
    if got[2][2] != BLACK or got[2][3] != BLACK or got[3][2] != BLACK:
        fail("classical changed a sub-pixel Scale2x leaves alone at the centre cell")
        return
    ok("the classical backend is Scale2x: it rounds a staircase corner nearest neighbour keeps")

    # Copy-only: no output colour that was not already in the source.
    out_sheet = root / "out-classical-sheet"
    if run_repaint(sheets, out_sheet, "--scale", "2", "--seam-width", "0", "--no-variants",
                   "--backend", "classical") is None:
        return
    got = png_read(out_sheet / "textures" / "sheets" / "metatiles.png")
    src = png_read(sheets / "metatiles.png")
    source_colours = {px for row in normalize(src) for px in row}
    invented = {px for row in got for px in row} - source_colours
    if invented:
        fail(f"classical invented {len(invented)} colour(s) not in the source, e.g. "
             f"{sorted(invented)[:3]} — a pixel-art scaler must only copy")
        return
    ok("the classical backend invents no colour: every output pixel is a source pixel")

    lost = [(x, y) for y in range(len(src)) for x in range(len(src[0]))
            if (src[y][x][3] == 0) != (got[y * 2][x * 2][3] == 0)]
    if lost:
        fail(f"classical changed transparency on {len(lost)} pixel(s), e.g. {lost[:3]}")
        return
    ok("the classical backend keeps the source alpha mask (ADR-0154 §7 still applies to it)")


# --- backends that are not installed here -----------------------------------


def test_esrgan_unavailable(root: Path, sheets: Path):
    """ADR-0154 §2: `esrgan` drives an install the user already has. With none
    it must name what to install and stop — never download, never half-write."""
    out = root / "out-esrgan"
    text = run_repaint(sheets, out, "--backend", "esrgan",
                       "--esrgan-binary", str(root / "nowhere" / "realesrgan-ncnn-vulkan"),
                       expect=1)
    if text is None:
        return
    for needle in ("never downloads", "realesrgan-ncnn-vulkan", "--backend classical"):
        if needle not in text:
            fail(f"the esrgan unavailable message does not mention {needle!r}: {text}")
            return
    if out.exists():
        fail("esrgan created an output tree before finding out it cannot run")
        return
    ok("esrgan with no local install exits 1 naming what to install, and writes nothing")


def test_diffusion_unavailable(root: Path, sheets: Path):
    """The four ways the diffusion backend can be unavailable. Each is a
    message a person can act on, and none of them touches the network: the
    non-loopback case is refused before a socket is opened."""
    cases = [
        (["--diffusion-endpoint", "http://example.com:8188"],
         ["not a loopback address", "Option B"],
         "a remote endpoint is refused outright"),
        (["--diffusion-endpoint", "http://127.0.0.1:9"],
         ["--diffusion-workflow is required"],
         "the ComfyUI path without a workflow says which flag is missing"),
        (["--diffusion-runner", str(root / "nowhere" / "generate.sh")],
         ["is not an executable on PATH"],
         "a runner that is not on PATH is reported as such"),
    ]
    for i, (extra, needles, label) in enumerate(cases):
        out = root / f"out-diffusion-{i}"
        text = run_repaint(sheets, out, "--backend", "diffusion", *extra, expect=1)
        if text is None:
            return
        for needle in needles:
            if needle not in text:
                fail(f"{label}: message does not mention {needle!r}: {text}")
                return
        if out.exists():
            fail(f"{label}: an output tree was created before the backend was probed")
            return
        ok(f"diffusion — {label}")

    workflow = root / "workflow.json"
    workflow.write_text(json.dumps({"1": {"class_type": "LoadImage",
                                         "inputs": {"image": "__CONTROL_IMAGE__"}}}),
                        encoding="utf-8")
    out = root / "out-diffusion-down"
    text = run_repaint(sheets, out, "--backend", "diffusion",
                       "--diffusion-endpoint", "http://127.0.0.1:9",
                       "--diffusion-workflow", str(workflow),
                       "--backend-timeout", "3", expect=1)
    if text is None:
        return
    if "no diffusion runtime answered" not in text or "ComfyUI path" not in text:
        fail(f"a closed local port does not produce the actionable message: {text}")
        return
    ok("diffusion — a local runtime that is not running exits 1 and says how to start one")


def test_diffusion_runner_driver(root: Path, sheets: Path):
    """The `diffusers` drive mode, exercised against a stub command.

    This proves the *driver* — argv order, the control image handed over, the
    result decoded, the size contract enforced. It proves nothing whatsoever
    about a diffusion model: no weights, no GPU and no model run here."""
    echo = root / "runner-echo.sh"
    echo.write_text('#!/bin/sh\ncp "$1" "$2"\n', encoding="utf-8")
    echo.chmod(0o755)
    out = root / "out-runner"
    if run_repaint(sheets, out, "--scale", "2", "--seam-width", "0", "--no-variants",
                   "--backend", "diffusion", "--diffusion-runner", str(echo)) is None:
        return
    got = png_read(out / "textures" / "sheets" / "metatiles.png")
    want = upscale(normalize(png_read(sheets / "metatiles.png")), 2)
    if got != want:
        fail("the runner drive mode did not round-trip the control image the stub echoed back")
        return
    ok("diffusion --diffusion-runner hands over the control image and decodes what comes back")

    small = root / "runner-small.py"
    small.write_text(
        "import sys, struct, zlib\n"
        "raw = b''.join(b'\\x00' + b'\\xff\\x00\\x00\\xff' * 2 for _ in range(2))\n"
        "def chunk(tag, data):\n"
        "    return struct.pack('>I', len(data)) + tag + data + struct.pack(\n"
        "        '>I', zlib.crc32(tag + data) & 0xFFFFFFFF)\n"
        "open(sys.argv[2], 'wb').write(b'\\x89PNG\\r\\n\\x1a\\n'\n"
        "    + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 6, 0, 0, 0))\n"
        "    + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))\n",
        encoding="utf-8")
    text = run_repaint(sheets, root / "out-runner-small", "--scale", "2",
                       "--backend", "diffusion",
                       "--diffusion-runner", f"{sys.executable} {small}", expect=1)
    if text is None:
        return
    if "returned 2x2" not in text or "resizing" not in text:
        fail(f"a wrong-sized backend answer is not rejected with a diagnosis: {text}")
        return
    ok("diffusion rejects an answer that is not the control image's size, and says why")

    text = run_repaint(sheets, root / "out-runner-false", "--backend", "diffusion",
                       "--diffusion-runner", "false", expect=1)
    if text is None:
        return
    if "exited 1" not in text:
        fail(f"a failing runner is not reported with its exit status: {text}")
        return
    ok("diffusion reports a runner that exits non-zero instead of writing a broken sheet")


class _FakeComfy(http.server.BaseHTTPRequestHandler):
    """The smallest thing that answers like a local ComfyUI: it accepts the
    upload, records the submitted graph and echoes the control image back as
    the 'generated' result. A stub for the transport — NOT a model."""

    state = {}

    def log_message(self, *_args):
        pass

    def _json(self, doc):
        body = json.dumps(doc).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/system_stats"):
            return self._json({"system": {"comfyui_version": "stub"}})
        if self.path.startswith("/history/"):
            return self._json({"pid-1": {
                "status": {"status_str": "success"},
                "outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "",
                                              "type": "output"}]}}}})
        if self.path.startswith("/view"):
            body = self.state.get("upload", b"")
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        self.send_error(404)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path.startswith("/upload/image"):
            head, _, rest = body.partition(b"\r\n\r\n")
            self.state["upload"] = rest.rsplit(b"\r\n--", 1)[0]
            self.state["upload_filename"] = head
            return self._json({"name": "control.png", "subfolder": "", "type": "input"})
        if self.path.startswith("/prompt"):
            self.state["prompt"] = json.loads(body.decode("utf-8"))
            return self._json({"prompt_id": "pid-1"})
        self.send_error(404)


def test_diffusion_comfy_driver(root: Path, sheets: Path):
    """The ComfyUI drive mode against a loopback stub: request construction
    (upload + placeholder substitution + /prompt), the poll, and the decode of
    /view. Again: transport only, no model, no weights, no GPU."""
    _FakeComfy.state = {}
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeComfy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        workflow = root / "workflow-full.json"
        workflow.write_text(json.dumps({
            "3": {"class_type": "KSampler",
                  "inputs": {"seed": "__SEED__", "denoise": "__DENOISE__",
                             "positive": "__PROMPT__", "width": "__WIDTH__"}},
            "10": {"class_type": "LoadImage", "inputs": {"image": "__CONTROL_IMAGE__"}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
        }), encoding="utf-8")
        out = root / "out-comfy"
        endpoint = f"http://127.0.0.1:{server.server_address[1]}"
        if run_repaint(sheets, out, "--scale", "2", "--seam-width", "0", "--no-variants",
                       "--backend", "diffusion", "--diffusion-endpoint", endpoint,
                       "--diffusion-workflow", str(workflow),
                       "--diffusion-prompt", "hand-painted 16-bit background",
                       "--diffusion-seed", "4242", "--sheets", "metatiles") is None:
            return
        got = png_read(out / "textures" / "sheets" / "metatiles.png")
        want = upscale(normalize(png_read(sheets / "metatiles.png")), 2)
        if got != want:
            fail("the ComfyUI drive mode did not decode the image the stub returned from /view")
            return
        ok("diffusion drives a local ComfyUI end to end: upload, queue, poll, /view, decode")

        graph = (_FakeComfy.state.get("prompt") or {}).get("prompt") or {}
        seed = ((graph.get("3") or {}).get("inputs") or {}).get("seed")
        if seed != 4242 or not isinstance(seed, int):
            fail(f"a quoted numeric placeholder did not become a number: seed is {seed!r}")
            return
        ok('"__SEED__" is substituted as a bare number, so numeric widget slots stay numeric')

        inputs = (graph.get("3") or {}).get("inputs") or {}
        image = ((graph.get("10") or {}).get("inputs") or {}).get("image")
        if image != "control.png":
            fail(f"the graph's control image is {image!r}, not the name the runtime gave the upload")
            return
        if inputs.get("positive") != "hand-painted 16-bit background":
            fail(f"the prompt was not substituted: {inputs.get('positive')!r}")
            return
        want_width = (COLUMNS * STRIDE + GUTTER) * 2
        if inputs.get("denoise") != 0.55 or inputs.get("width") != want_width:
            fail(f"denoise/width placeholders are wrong: {inputs.get('denoise')!r}, "
                 f"{inputs.get('width')!r} (want 0.55 and {want_width})")
            return
        ok("the control image, prompt, denoise and target width reach the workflow substituted")
    finally:
        server.shutdown()
        server.server_close()


# --- the primary target: captured screens ------------------------------------


def test_target_screens(root: Path):
    """ADR-0154 §2 as re-scoped: `--target screens` repaints the captured
    scenes, discovered by reading the recorder's condition-prefixed
    <background> lines, and re-emits a manifest that keeps them."""
    textures = make_screens_fixture(root)
    out = root / "out-screens"
    text = run_repaint(textures.parent.parent, out, "--target", "screens", "--scale", "2")
    if text is None:
        return

    got = png_read(out / "textures" / "backgrounds" / "screen001.png")
    if got != upscale(normalize(png_read(textures / "backgrounds" / "screen001.png")), 2):
        fail("the repainted screen is not the upscale of the captured one")
        return
    if not (out / "textures" / "backgrounds" / "screen001.orig.png").is_file():
        fail("the .orig.png twin was not carried across")
        return
    ok("--target screens repaints backgrounds/screenNNN.png and keeps the .orig.png twin")

    manifest = (out / "textures" / "hires.txt").read_text(encoding="utf-8")
    if SCREEN_LINE not in manifest:
        fail(f"the condition-prefixed <background> line was not preserved verbatim:\n{manifest}")
        return
    if f"<scale>{SCREEN_SCALE * 2}" not in manifest:
        fail(f"<scale> was not multiplied by the repaint factor:\n{manifest}")
        return
    ok("the repaint's hires.txt keeps the prefixed <background> line and multiplies <scale>")

    if "screen001_A,tileAtPosition" not in manifest or "screen001_B,tileAtPosition" not in manifest:
        fail(f"a <condition> the kept entry references is missing:\n{manifest}")
        return
    if "unused_C" in manifest:
        fail("a <condition> nothing references was copied into the repaint's manifest")
        return
    if "<img>" in manifest or "<tile>" in manifest:
        fail("the repaint's manifest points at <img>/<tile> files it does not ship")
        return
    if "screen002" in manifest:
        fail("a <background> whose file does not exist was kept in the manifest")
        return
    if "screen002" not in text:
        fail("the missing <background> file was skipped silently")
        return
    ok("only the referenced <condition> lines survive; a missing screen is skipped and reported")

    doc = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    if (doc.get("generated") or {}).get("scale") != SCREEN_SCALE * 2:
        fail(f"pack.json's 'generated' does not record the effective scale: {doc.get('generated')}")
        return
    ok("the screen repaint is labelled generated with the effective (source x factor) scale")


# --- the catalog's disclosure column -----------------------------------------


def test_catalog_generated_column():
    """ADR-0154 §3: the `generated` object is disclosure, surfaced as a
    column. It is never a verdict, so nothing here refuses a pack."""
    sys.path.insert(0, str(REPO / "scripts"))
    import mei_catalog_entry as entry_mod
    import community_pack_markdown as markdown
    import pack_generated_disclosure as disclosure
    import generate_community_pack_catalog as generator  # noqa: F401 -- the facade wires it

    if entry_mod.generated_field(None) is not None:
        fail("generated_field invented a label out of no mep-meta")
        return
    if entry_mod.generated_field({"author": "someone"}) is not None:
        fail("a pack that declares nothing was reported as generated")
        return
    if entry_mod.generated_field({"generated": "yes"}) is not None:
        fail("a non-object 'generated' was accepted as a declaration")
        return
    full = entry_mod.generated_field({"generated": {
        "by": "sheet_repaint", "backend": "diffusion", "date": "2026-09-05",
        "scale": 4, "source": "auto/textures", "extra": "ignored"}})
    if full != {"by": "sheet_repaint", "backend": "diffusion", "date": "2026-09-05",
                "scale": 4, "source": "auto/textures"}:
        fail(f"generated_field did not copy exactly the catalog's fields: {full}")
        return
    if entry_mod.generated_field({"generated": {}}) != {"by": "?", "backend": "?"}:
        fail("presence of the object is the label — a malformed one must still disclose")
        return
    ok("generated_field reads MEP v1.6's root object, degrades a malformed one, invents nothing")

    entry, _mismatch = entry_mod.build_pack_entry(
        7, "Game", "nes", "CC0-1.0", "https://example.invalid/p.zip", "a" * 64, ROM_SHA1,
        entry_mod.STATUS_HD_PARCIAL, {"generated": {"by": "sheet_repaint", "backend": "classical"}})
    if entry.get("generated") != {"by": "sheet_repaint", "backend": "classical"}:
        fail(f"the MEI entry does not carry the disclosure: {entry.get('generated')}")
        return
    if entry.get("verdict") == "invalid" or "kind" not in entry:
        fail("a generated pack was treated as anything other than a normal accepted entry")
        return
    ok("a generated pack still builds a normal MEI entry, with 'generated' alongside it")

    rows = [
        {"jogo": "Hand", "console": "nes", "autor": "an artist", "data": "2026-01-01",
         "url": "https://github.com/o/r/issues/13", "thumbs_up": 5, "errata_count": 0,
         "generated": None},
        {"jogo": "Machine", "console": "nes", "autor": "?", "data": "2026-01-02",
         "url": "https://github.com/o/r/issues/132", "thumbs_up": 2, "errata_count": 0,
         "generated": {"by": "sheet_repaint", "backend": "diffusion"}},
    ]
    text = disclosure.with_generated_column(markdown.build_markdown(rows), rows,
                                            markdown.TABLE_HEADER, markdown.TABLE_SEP,
                                            markdown.POPULARITY_NOTE)
    table = [line for line in text.split("\n") if line.startswith("|")]
    if not table[0].endswith(" Generated |"):
        fail(f"the table header has no disclosure column: {table[0]}")
        return
    if len({line.count("|") for line in table}) != 1:
        fail(f"the column count is not uniform across the table: {table}")
        return
    machine = [line for line in table if "issues/132" in line]
    hand = [line for line in table if "issues/13)" in line]
    if len(machine) != 1 or not machine[0].endswith("machine (diffusion) |"):
        fail(f"the generated row does not disclose its backend: {machine}")
        return
    if len(hand) != 1 or not hand[0].endswith(f"{disclosure.GENERATED_EMPTY} |"):
        fail(f"a hand-drawn row was marked as generated: {hand}")
        return
    ok("the catalog table gains a Generated column naming the backend, empty for artist packs")

    if disclosure.GENERATED_NOTE not in text:
        fail("the table explains nothing about what the column means")
        return
    plain = [dict(rows[0]), dict(rows[1], generated=None)]
    if disclosure.GENERATED_NOTE in disclosure.with_generated_column(
            markdown.build_markdown(plain), plain, markdown.TABLE_HEADER,
            markdown.TABLE_SEP, markdown.POPULARITY_NOTE):
        fail("the note is printed on a catalog where no pack is generated")
        return
    ok("the column's note appears only when some pack in the catalog declares itself generated")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _game, sheets = make_fixture(root)
        test_passthrough_structure(root, sheets)
        test_seam_pass_touches_only_borders(root, sheets)
        test_alpha_survives(root, sheets)
        test_palette_variant_recolour(root, sheets)
        test_pack_json_label(root, sheets)
        test_survives_mep_build(root, sheets)
        test_no_sheets_is_an_error(root)
        test_classical_backend(root, sheets)
        test_esrgan_unavailable(root, sheets)
        test_diffusion_unavailable(root, sheets)
        test_diffusion_runner_driver(root, sheets)
        test_diffusion_comfy_driver(root, sheets)
        test_target_screens(root)
        test_catalog_generated_column()
    print(f"{PASSED} check(s) passed, {'some failed' if FAILED else 'none failed'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
