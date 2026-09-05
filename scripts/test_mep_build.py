#!/usr/bin/env python3
"""Acceptance test for scripts/mep_build.py (PRD F5.4c, ADR-0049 §2).

Builds a synthetic author folder (a 16-column sheet + a key-source
hires.txt + two OGGs) and asserts the whole build/pack/rename cycle:

  * `build` re-points every tile key at the sheet cell that owns it (16px
    crops at scale 2, img index = sheet index), regenerates audio/hires.txt
    with the OGG ids taken from their file names, and lints clean;
  * `pack` writes a correct pack.json (sections from the tree, targets from
    the ROM) and produces a byte-deterministic zip that lints clean;
  * `rename-audio-id` renames an enumerated id across fingerprints.json +
    the midi/bgm/sfx files + the audio/hires.txt references;
  * the failure modes exit 2 with a clear message: no key source, sheet
    cells < tile keys, a non-16-column sheet;
  * the ADR-0153 (F9.4) sheet round-trip: `textures/sheets/*.json` +
    `*.png` are sliced back into per-tile crops — identity is pixel-exact
    (PRD Phase 9 validation test 6), painting one cell touches exactly that
    cell's tiles, a 2x upscaled sheet slices at scale 2, a map slices
    through `placements[]`, null/short `tiles[]` entries are skipped rather
    than fatal, and a non-integer scale is a build error;
  * the ADR-0153 §4 claim rule: a cell claims a tile key only when it was
    painted, measured against its `*.orig.png` twin — so a painted
    `metatiles.png` cell beats an untouched map (PRD test 3) and a painted
    map beats the untouched vocabulary (PRD test 4), with the static kind
    rank as the tie-break when both, or neither, were painted.

Framework-free, mirroring test_mep_recipe.py's ok()/fail()/main() style.
Wired into `make doc-checks`. Usage: python3 scripts/test_mep_build.py
"""

import hashlib
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MEP_BUILD = REPO / "scripts" / "mep_build.py"
GEN_ROM = REPO / "scripts" / "gen_synthetic_nrom.py"
PY = sys.executable

FAILED = 0


def ok(msg):
    print(f"PASS: {msg}")


def fail(msg):
    global FAILED
    FAILED = 1
    print(f"FAIL: {msg}")


def png(width, height, rgba=(0xC8, 0x28, 0x28, 0xFF)) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgba) * width for _ in range(height))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


# --- ADR-0153 (F9.4) sheet fixtures ----------------------------------------
#
# The C++ emitter (Core/NES/HdPacks/SheetRender.cpp) is the ground truth for
# both the pixels and the sidecar bytes, so the helpers below are a faithful
# Python mirror of RenderTile / RenderMetatile / BuildContactSheet /
# SerializeSheet. Any drift here would make the round-trip test lie.

# Stand-in NES master palette: 64 distinct 0x00RRGGBB entries. The real one
# lives in HdPackBuilder; only its indexing matters to the round-trip.
NES_PALETTE = [((i * 4) << 16) | ((i * 3 + 7) << 8) | (i * 2 + 3) for i in range(64)]


def tile_bytes(shape: int) -> bytes:
    """A distinct, non-degenerate 2bpp pattern per shape id."""
    lo = bytes((shape * 7 + r * 13) & 0xFF for r in range(8))
    hi = bytes((shape * 11 + r * 5) & 0xFF for r in range(8))
    return lo + hi


def tile_hex(shape: int) -> str:
    return tile_bytes(shape).hex().upper()


PAL_WORD = 0x0F162A30
PAL_HEX = f"{PAL_WORD:08X}"


def render_tile(shape: int, pixels, x: int, y: int, width: int, height: int):
    """SheetRender::RenderTile: opaque on all four colour indexes."""
    colors = [NES_PALETTE[(PAL_WORD >> ((3 - c) * 8)) & 0x3F] | 0xFF000000 for c in range(4)]
    data = tile_bytes(shape)
    for row in range(8):
        py = y + row
        if not 0 <= py < height:
            continue
        lo, hi = data[row], data[row + 8]
        for col in range(8):
            px = x + col
            if not 0 <= px < width:
                continue
            bit = 7 - col
            pixels[py][px] = colors[((lo >> bit) & 1) | (((hi >> bit) & 1) << 1)]


def blank(width: int, height: int):
    return [[0] * width for _ in range(height)]


def png_rgba(pixels) -> bytes:
    """Encode 0xAARRGGBB rows as a non-interlaced 8-bit RGBA PNG, filter 0."""
    height, width = len(pixels), len(pixels[0])
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for p in row:
            raw += bytes(((p >> 16) & 0xFF, (p >> 8) & 0xFF, p & 0xFF, (p >> 24) & 0xFF))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def png_read(path: Path):
    """Decode a filter-0 8-bit RGBA PNG back into 0xAARRGGBB rows."""
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
        rows.append([(line[i + 3] << 24) | (line[i] << 16) | (line[i + 1] << 8) | line[i + 2]
                     for i in range(0, stride, 4)])
    return rows


def upscale(pixels, n: int):
    return [[p for p in row for _ in range(n)] for row in pixels for _ in range(n)]


def crop(pixels, x: int, y: int, size: int):
    return [row[x:x + size] for row in pixels[y:y + size]]


def _fixed(v):
    return f"{v:.4f}"


def _tiles_json(tiles):
    parts = []
    for t in tiles:
        parts.append("null" if t is None else f'{{ "tile": "{tile_hex(t)}", "palette": "{PAL_HEX}" }}')
    return "[" + ", ".join(parts) + "]"


def serialize_sheet(kind, unit, gutter, columns, sheet, reference, cells,
                    placements=None, mode=None, hud_rows=0, version=1):
    """Byte-shape mirror of SheetRender::SerializeSheet (ADR-0153 §4)."""
    out = ["{\n", f'  "version": {version},\n', f'  "kind": "{kind}",\n',
           f'  "gridUnit": {unit},\n', '  "gridPhase": { "x": 0, "y": 0 },\n',
           f'  "gridConsistency": {{ "chosen": {_fixed(0.83)}, "alt8x8": {_fixed(0.41)} }},\n',
           f'  "cell": {{ "w": {unit}, "h": {unit} }},\n', f'  "gutter": {gutter},\n',
           f'  "columns": {columns},\n', f'  "sheet": "{sheet}",\n',
           f'  "reference": "{reference}",\n']
    if placements is not None:
        out.append(f'  "mode": "{mode or "screen"}",\n')
        out.append(f'  "hudRows": {hud_rows},\n')
        out.append("  \"placements\": [")
        body = [f'{{ "x": {p[0]}, "y": {p[1]}, "cell": {p[2]} }}' for p in placements]
        out.append(("\n    " + ",\n    ".join(body) + "\n  ],\n") if body else "],\n")
    out.append("  \"cells\": [")
    body = []
    for c in cells:
        meta = f', "metatile": {c["metatile"]}' if c.get("metatile") is not None else ""
        alias = ""
        if c.get("aliases"):
            parts = [f'{{ "metatile": {a["metatile"]}, "tiles": {_tiles_json(a["tiles"])} }}'
                     for a in c["aliases"]]
            alias = f', "aliases": [{", ".join(parts)}]'
        body.append(f'{{ "index": {c["index"]}, "x": {c["x"]}, "y": {c["y"]}, "count": {c["count"]}, '
                    f'"context": "{c["context"]}"{meta}{alias}, "label": "", "tiles": {_tiles_json(c["tiles"])} }}')
    out.append(("\n    " + ",\n    ".join(body) + "\n  ]\n") if body else "]\n")
    out.append("}\n")
    return "".join(out)


def contact_sheet(unit, gutter, columns, vocab_cells):
    """BuildContactSheet: `columns` cells per row, gutter around and between,
    transparent everywhere a tile did not draw. Returns (cells, 1x pixels)."""
    stride = unit + gutter
    rows = (len(vocab_cells) + columns - 1) // columns
    width, height = columns * stride + gutter, rows * stride + gutter
    pixels = blank(width, height)
    cells = []
    per = 4 if unit >= 16 else 1
    for i, cell in enumerate(vocab_cells):
        x = gutter + (i % columns) * stride
        y = gutter + (i // columns) * stride
        for k in range(per):
            shape = cell["tiles"][k] if k < len(cell["tiles"]) else None
            if shape is None:
                continue
            render_tile(shape, pixels, x + (k % 2) * 8, y + (k // 2) * 8, width, height)
        cells.append(dict(cell, index=i, x=x, y=y))
    return cells, pixels


def map_sheet(unit, placements, vocab_cells, width, height):
    """RenderMap: every placement at its map-pixel origin, no gutter."""
    pixels = blank(width, height)
    per = 4 if unit >= 16 else 1
    for px, py, idx in placements:
        for k in range(per):
            tiles = vocab_cells[idx]["tiles"]
            shape = tiles[k] if k < len(tiles) else None
            if shape is None:
                continue
            render_tile(shape, pixels, px + (k % 2) * 8, py + (k // 2) * 8, width, height)
    return pixels


def write_pair(sheets: Path, stem: str, pixels, scale: int):
    """The sheet at `scale` plus its pixel-exact 1x `*.orig.png` twin — the
    F5.4d `_writeReferences` convention the edited-cell test measures against."""
    (sheets / f"{stem}.png").write_bytes(png_rgba(upscale(pixels, scale) if scale > 1 else pixels))
    (sheets / f"{stem}.orig.png").write_bytes(png_rgba(pixels))


def parse_hires(path: Path):
    """(img list, {(tileData, palette): (img index, x, y, fields)})."""
    imgs, tiles = [], {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("<img>"):
            imgs.append(s[5:].strip())
        elif "<tile>" in s and not s.startswith("#"):
            f = [t.strip() for t in s.split("<tile>", 1)[1].split(",")]
            tiles[(f[1].upper(), f[2].upper())] = (int(f[0]), int(f[3]), int(f[4]), f)
    return imgs, tiles


def make_sheet_folder(root: Path, name: str, scale: int = 1):
    """An ADR-0153 author folder: a metatile vocabulary of 6 cells, a stitched
    map over cells 0..3, and an object over cells 0..1."""
    folder = root / name
    sheets = folder / "textures" / "sheets"
    sheets.mkdir(parents=True)
    unit, gutter, columns = 16, 1, 3
    # Cells 4 and 5 exercise the "no art" paths: a null in the middle of
    # tiles[] (the entries after it must NOT shift up) and a short tiles[].
    vocab = [
        {"count": 431, "context": "scene", "metatile": 0, "tiles": [0, 1, 2, 3]},
        {"count": 300, "context": "scene", "metatile": 1, "tiles": [4, 5, 6, 7]},
        {"count": 120, "context": "scene", "metatile": 2, "tiles": [8, 9, 10, 11]},
        {"count": 90, "context": "scene", "metatile": 3, "tiles": [12, 13, 14, 15]},
        {"count": 12, "context": "scene", "metatile": 4, "tiles": [16, None, 17, None]},
        {"count": 3, "context": "scene", "metatile": 5, "tiles": [18, 19]},
    ]
    cells, pixels = contact_sheet(unit, gutter, columns, vocab)
    write_pair(sheets, "metatiles", pixels, scale)
    (sheets / "metatiles.json").write_text(
        serialize_sheet("metatiles", unit, gutter, columns, "metatiles.png", "metatiles.orig.png", cells),
        encoding="utf-8")

    placements = [(0, 0, 0), (16, 0, 1), (0, 16, 2), (16, 16, 3)]
    write_pair(sheets, "map-000", map_sheet(unit, placements, vocab, 32, 32), scale)
    (sheets / "map-000.json").write_text(
        serialize_sheet("map", unit, 0, 1, "map-000.png", "map-000.orig.png", [],
                        placements=placements, mode="screen"),
        encoding="utf-8")

    obj_cells, obj_pixels = contact_sheet(unit, gutter, 2, vocab[:2])
    write_pair(sheets, "obj000", obj_pixels, scale)
    (sheets / "obj000.json").write_text(
        serialize_sheet("object", unit, gutter, 2, "obj000.png", "obj000.orig.png", obj_cells),
        encoding="utf-8")

    # Key source: only cells 0..1 are known keys, and tile 0 carries
    # non-default brightness/defaultTile that the build must carry over.
    lines = ["<ver>107", "<scale>2", "<system>nes",
             "<supportedRom>2A4E126D0286BEA0BF503C80A12352C57539F76B", "<img>old.png"]
    for shape in range(8):
        extra = "0.5,Y" if shape == 0 else "1,N"
        lines.append(f"<tile>0,{tile_hex(shape)},{PAL_HEX},0,0,{extra}")
    (folder / "textures" / "hires.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder, vocab, cells


def assert_pixel_exact(folder: Path, tiles, scale: int, label: str):
    """PRD Phase 9 validation test 6: every emitted crop must be byte-identical
    to what SheetRender::RenderMetatile drew for that key."""
    sheets = folder / "textures" / "sheets"
    cache = {}
    span = 8 * scale
    for shape in range(20):
        key = (tile_hex(shape), PAL_HEX)
        if key not in tiles:
            continue
        img_index, x, y, _f = tiles[key]
        imgs, _ = parse_hires(folder / "textures" / "hires.txt")
        rel = imgs[img_index]
        if rel not in cache:
            cache[rel] = png_read(sheets / Path(rel).name)
        got = crop(cache[rel], x, y, span)
        want_1x = blank(8, 8)
        render_tile(shape, want_1x, 0, 0, 8, 8)
        want = upscale(want_1x, scale) if scale > 1 else want_1x
        if got != want:
            fail(f"{label}: crop for shape {shape} at {rel}({x},{y}) is not pixel-identical to RenderMetatile")
            return False
    ok(f"{label}: every sliced crop is pixel-identical to what the builder drew")
    return True


def paint(folder: Path, png_name: str, x: int, y: int, size: int, color: int = 0xFFA020F0):
    """Paint a `size`x`size` block into a sheet, leaving its `*.orig.png` twin
    untouched — exactly what an artist does in an image editor."""
    path = folder / "textures" / "sheets" / png_name
    px = png_read(path)
    for py in range(y, min(y + size, len(px))):
        for pxx in range(x, min(x + size, len(px[0]))):
            px[py][pxx] = color
    path.write_bytes(png_rgba(px))


def edited_precedence_tests(root: Path):
    """ADR-0153 §4: a cell claims a tile key only when it was actually painted,
    measured against the `*.orig.png` twin. This is what lets PRD Phase 9
    validation tests 3 (paint a bush in metatiles.png) and 4 (paint a seam in
    map-NNN.png) both work — no static order can satisfy both."""
    shapes = (8, 9, 10, 11)  # metatile 2: on metatiles.png AND on map-000.png

    def owners(folder):
        imgs, tiles = parse_hires(folder / "textures" / "hires.txt")
        return {imgs[tiles[(tile_hex(s), PAL_HEX)][0]] for s in shapes}

    # PRD test 3: paint one metatile cell; the untouched map must not win.
    a, _v, cells = make_sheet_folder(root, "edited-metatiles")
    paint(a, "metatiles.png", cells[2]["x"], cells[2]["y"], 16)
    out = run("build", str(a))
    if out is None:
        return
    if owners(a) != {"sheets/metatiles.png"}:
        fail(f"a painted metatile cell lost to an untouched map: {owners(a)}")
    elif "(painted)" not in out:
        fail(f"the painted cell's win over the untouched map was not logged:\n{out}")
    else:
        ok("PRD test 3: a painted metatiles.png cell beats an untouched map covering the same key")

    # PRD test 4: paint the map; the untouched vocabulary must not win.
    b, _v, _c = make_sheet_folder(root, "edited-map")
    paint(b, "map-000.png", 0, 16, 16)
    out = run("build", str(b))
    if out is None:
        return
    if owners(b) != {"sheets/map-000.png"}:
        fail(f"a painted map lost to the untouched metatile vocabulary: {owners(b)}")
    elif "(untouched)" not in out:
        fail(f"the untouched vocabulary's loss was not logged:\n{out}")
    else:
        ok("PRD test 4: a painted map-NNN.png region beats the untouched metatile vocabulary")

    # Both painted: the static rank breaks the tie (map > metatiles), logged.
    c, _v, c_cells = make_sheet_folder(root, "edited-both")
    paint(c, "metatiles.png", c_cells[2]["x"], c_cells[2]["y"], 16)
    paint(c, "map-000.png", 0, 16, 16, color=0xFF20A0F0)
    out = run("build", str(c))
    if out is None:
        return
    if owners(c) != {"sheets/map-000.png"}:
        fail(f"two painted sheets did not fall back to the static rank: {owners(c)}")
    elif "(precedence)" not in out:
        fail(f"the static-rank override was not logged:\n{out}")
    else:
        ok("both painted: the static rank decides (map > metatiles) and the override is logged")

    # A sheet with no reference twin has nothing to diff against: every cell
    # counts as painted, and the static rank keeps deciding.
    d, _v, _c = make_sheet_folder(root, "edited-blind")
    (d / "textures" / "sheets" / "map-000.orig.png").unlink()
    out = run("build", str(d))
    if out is None:
        return
    if owners(d) != {"sheets/map-000.png"}:
        fail(f"a twin-less sheet did not fall back to the static rank: {owners(d)}")
    elif "every cell counts as painted" not in out:
        fail(f"a missing reference twin was not reported:\n{out}")
    else:
        ok("a sheet with no *.orig.png twin counts as fully painted and keeps its static rank")


def sheet_alias_tests(root: Path):
    """ADR-0153 §3 alias pass (F9.7): a cell absorbs the vocabulary entries that
    render to the same pixels, and the build must emit a <tile> for every one of
    them from the single painted crop. Without the fan-out a bank-swapped
    duplicate would keep its old art and the two copies would drift apart on
    screen - which is exactly what happened when each was painted by hand."""
    folder, vocab, cells = make_sheet_folder(root, "sheets-alias")
    sheets = folder / "textures" / "sheets"
    # Cell 4 absorbs two entries that render identically under other keys. It is
    # deliberately a metatiles-only cell: cells 0..3 also appear on the map and
    # object sheets, where the §4 precedence rule would resolve the canonical
    # key from a higher-ranked sheet than the alias, and the comparison below
    # would be measuring precedence rather than the fan-out.
    cells[4]["aliases"] = [{"metatile": 6, "tiles": [40, None, 41, None]},
                           {"metatile": 7, "tiles": [44, None, 45, None]}]
    (sheets / "metatiles.json").write_text(
        serialize_sheet("metatiles", 16, 1, 3, "metatiles.png", "metatiles.orig.png", cells),
        encoding="utf-8")

    out = run("build", str(folder))
    if out is None:
        return
    _imgs, tiles = parse_hires(folder / "textures" / "hires.txt")
    # The 20 keys of the base fixture plus 2 aliases x 2 resolved tiles.
    if len(tiles) != 24:
        fail(f"alias fan-out emitted {len(tiles)} keys, expected 24")
    else:
        ok("an aliased cell emits a <tile> for its own keys and for every alias")

    canonical = tiles.get((tile_hex(16), PAL_HEX))
    absorbed = [tiles.get((tile_hex(40), PAL_HEX)), tiles.get((tile_hex(44), PAL_HEX))]
    if canonical is None or any(a is None for a in absorbed):
        fail("an alias key is missing from the built hires.txt")
    elif not all(a[:3] == canonical[:3] for a in absorbed):
        fail("an alias was not painted from the canonical cell's crop")
    else:
        ok("every alias takes its art from the canonical cell's crop, so they cannot drift")


def sheet_round_trip_tests(root: Path):
    # --- identity round-trip, precedence, null/short tiles[] ---
    folder, vocab, cells = make_sheet_folder(root, "sheets-1x")
    out = run("build", str(folder))
    if out is None:
        return
    hires = folder / "textures" / "hires.txt"
    imgs, tiles = parse_hires(hires)
    # 4 cells x 4 + cell 4 (2 tiles) + cell 5 (2 tiles) = 20 distinct keys.
    if len(tiles) != 20:
        fail(f"sheet build emitted {len(tiles)} distinct tile keys, expected 20")
    else:
        ok("sheet build emits one <tile> per resolved 8x8 crop (20 keys)")
    if "sheets/metatiles.orig.png" in imgs or any(".orig.png" in i for i in imgs):
        fail(f"*.orig.png reference twin was sliced: {imgs}")
    else:
        ok("*.orig.png reference twins are never sliced nor emitted")
    if "<scale>1" not in hires.read_text(encoding="utf-8"):
        fail("build did not take <scale> from the 1x sheet art")
    else:
        ok("build takes <scale> from the sheet art when nothing else pins it")

    # Precedence: object (rank 4) > map (3) > metatiles (1).
    def img_of(shape):
        return imgs[tiles[(tile_hex(shape), PAL_HEX)][0]]

    if img_of(0) != "sheets/obj000.png" or img_of(5) != "sheets/obj000.png":
        fail(f"object sheet did not win over map/metatiles: {img_of(0)}, {img_of(5)}")
    elif img_of(8) != "sheets/map-000.png" or img_of(15) != "sheets/map-000.png":
        fail(f"map did not win over the metatile vocabulary: {img_of(8)}, {img_of(15)}")
    elif img_of(16) != "sheets/metatiles.png" or img_of(18) != "sheets/metatiles.png":
        fail(f"metatile-only cells did not stay on metatiles.png: {img_of(16)}, {img_of(18)}")
    else:
        ok("precedence metatiles < map < object holds, overrides are logged")
    if "overrides tile" not in out:
        fail(f"an override was applied without being logged:\n{out}")
    else:
        ok("every precedence override is logged")

    # The map is sliced through placements[], resolved against the sibling
    # metatiles.json vocabulary: metatile 2 is placed at map pixel (0,16), so
    # its four 8x8 tiles land row-major inside that 16x16 cell.
    map_at = {shape: tiles[(tile_hex(shape), PAL_HEX)][1:3] for shape in (8, 9, 10, 11)}
    if map_at != {8: (0, 16), 9: (8, 16), 10: (0, 24), 11: (8, 24)}:
        fail(f"map not sliced through placements[]: {map_at}")
    else:
        ok("a map is sliced through placements[] against the metatile vocabulary")

    # Cell 4 is [shape16, null, shape17, null]: the null must be skipped
    # without shifting shape17 up out of the cell's second row.
    c4 = cells[4]
    if tiles[(tile_hex(16), PAL_HEX)][1:3] != (c4["x"], c4["y"]):
        fail(f"null-skipping shifted the first tile of cell 4: {tiles[(tile_hex(16), PAL_HEX)][1:3]}")
    elif tiles[(tile_hex(17), PAL_HEX)][1:3] != (c4["x"], c4["y"] + 8):
        fail(f"a null tiles[] entry shifted the entries after it: {tiles[(tile_hex(17), PAL_HEX)][1:3]}")
    else:
        ok("a null tiles[] entry is skipped without shifting the entries after it")
    c5 = cells[5]
    if tiles[(tile_hex(19), PAL_HEX)][1:3] != (c5["x"] + 8, c5["y"]):
        fail(f"short tiles[] mis-sliced: {tiles[(tile_hex(19), PAL_HEX)][1:3]}")
    else:
        ok("a short tiles[] is sliced for what it has, not fatal")

    # Key-source attributes carried over; unknown keys default to 1,N.
    if tiles[(tile_hex(0), PAL_HEX)][3][5:7] != ["0.5", "Y"]:
        fail(f"key-source brightness/defaultTile not carried over: {tiles[(tile_hex(0), PAL_HEX)][3]}")
    elif tiles[(tile_hex(16), PAL_HEX)][3][5:7] != ["1", "N"]:
        fail(f"a sheet-only key did not default to 1,N: {tiles[(tile_hex(16), PAL_HEX)][3]}")
    else:
        ok("<tile> attributes carry over from the key source, sheet-only keys default to 1,N")

    # Nothing has been painted yet, so no cell claims anything: the static
    # rank decides and the identity round-trip must stay pixel-exact.
    assert_pixel_exact(folder, tiles, 1, "identity round-trip (nothing painted)")

    # --- painting a cell changes exactly that cell's tiles ---
    sheets_dir = folder / "textures" / "sheets"
    before = {rel: png_read(sheets_dir / Path(rel).name) for rel in imgs}
    painted = png_read(sheets_dir / "metatiles.png")
    for y in range(c4["y"], c4["y"] + 16):
        for x in range(c4["x"], c4["x"] + 16):
            painted[y][x] = 0xFF00FF00
    (sheets_dir / "metatiles.png").write_bytes(png_rgba(painted))
    if run("build", str(folder)) is None:
        return
    imgs2, tiles2 = parse_hires(hires)
    if imgs2 != imgs or set(tiles2) != set(tiles):
        fail("painting a cell changed the manifest's img list or key set")
    else:
        now = {rel: png_read(sheets_dir / Path(rel).name) for rel in imgs2}
        changed = set()
        for key, (idx, x, y, _f) in tiles2.items():
            rel = imgs2[idx]
            if crop(now[rel], x, y, 8) != crop(before[rel], x, y, 8):
                changed.add(key)
        want = {(tile_hex(16), PAL_HEX), (tile_hex(17), PAL_HEX)}
        if changed != want:
            fail(f"painting cell 4 changed {len(changed)} tile(s), expected exactly its 2: {sorted(k[0][:4] for k in changed)}")
        else:
            ok("painting one cell changes exactly the tiles of that cell, nothing else")

    # --- a 2x upscaled sheet slices at scale 2 ---
    up, _v, up_cells = make_sheet_folder(root, "sheets-2x", scale=2)
    if run("build", str(up)) is not None:
        up_imgs, up_tiles = parse_hires(up / "textures" / "hires.txt")
        if "<scale>2" not in (up / "textures" / "hires.txt").read_text(encoding="utf-8"):
            fail("a 2x sheet did not produce <scale>2")
        elif up_tiles[(tile_hex(16), PAL_HEX)][1:3] != (up_cells[4]["x"] * 2, up_cells[4]["y"] * 2):
            fail(f"2x sheet not sliced at scale 2: {up_tiles[(tile_hex(16), PAL_HEX)][1:3]}")
        else:
            ok("an upscaled (2x) sheet is sliced at scale 2")
        assert_pixel_exact(up, up_tiles, 2, "2x round-trip")

    # --- a non-integer ratio is a build error naming both sizes ---
    bad, _v, _c = make_sheet_folder(root, "sheets-bad")
    px = png_read(bad / "textures" / "sheets" / "metatiles.png")
    px = [row + [0] for row in px]  # 52 -> 53 px wide: not a whole multiple
    (bad / "textures" / "sheets" / "metatiles.png").write_bytes(png_rgba(px))
    out = run("build", str(bad), expect=2)
    if out is not None and "metatiles.png" in out and "53x35" in out and "52x35" in out:
        ok("a non-integer sheet scale is an error naming the file and both sizes")
    else:
        fail(f"non-integer sheet scale: {out}")

    # --- a map with no sibling metatiles.json is skipped, not fatal ---
    orphan, _v, _c = make_sheet_folder(root, "sheets-orphan")
    for stem in ("metatiles", "obj000"):
        for suffix in (".json", ".png", ".orig.png"):
            f = orphan / "textures" / "sheets" / f"{stem}{suffix}"
            if f.exists():
                f.unlink()
    out = run("build", str(orphan))
    if out is not None and "no sibling metatiles.json" in out:
        ok("a map without its metatile vocabulary is skipped with a warning")
    else:
        fail(f"orphan map: {out}")

    # --- an unknown sidecar version is skipped, never a crash ---
    future, _v, _c = make_sheet_folder(root, "sheets-future")
    fj = future / "textures" / "sheets" / "metatiles.json"
    fj.write_text(fj.read_text(encoding="utf-8").replace('"version": 1', '"version": 2'), encoding="utf-8")
    out = run("build", str(future))
    if out is not None and "is not 1" in out:
        ok("an unknown sidecar version is skipped with a clear warning")
    else:
        fail(f"unknown sheet version: {out}")

    edited_precedence_tests(root)


def run(*argv, expect=0, cwd=None):
    p = subprocess.run([PY, str(MEP_BUILD), *argv], capture_output=True, text=True, cwd=cwd)
    out = (p.stdout + p.stderr).strip()
    if p.returncode != expect:
        fail(f"mep_build {' '.join(argv)} -> exit {p.returncode}, expected {expect}: {out}")
        return None
    return out


def make_author_folder(root: Path, keys: int = 16, name: str = "author"):
    """A buildable author folder: a 16-column sheet at scale 2 (16px cells),
    a key-source hires.txt, and one bgm + one sfx OGG."""
    folder = root / name
    (folder / "textures" / "sheets").mkdir(parents=True)
    (folder / "audio" / "bgm").mkdir(parents=True)
    (folder / "audio" / "sfx").mkdir(parents=True)
    (folder / "textures" / "sheets" / "objects.png").write_bytes(png(256, 16))  # 16 cells, scale 2
    lines = ["<ver>107", "<scale>2", "<system>nes",
             "<supportedRom>2A4E126D0286BEA0BF503C80A12352C57539F76B", "<img>old.png"]
    for k in range(keys):
        lines.append(f"<tile>0,{k:02X}{'00' * 15},0F001A2C,0,0,1,N")
    (folder / "textures" / "hires.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / "audio" / "bgm" / "01.ogg").write_bytes(b"")
    (folder / "audio" / "sfx" / "03.ogg").write_bytes(b"")
    return folder


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = make_author_folder(root)

        # --- build ---
        out = run("build", str(folder))
        if out is None:
            return 1
        hires = folder / "textures" / "hires.txt"
        text = hires.read_text(encoding="utf-8")
        tiles = [l for l in text.splitlines() if "<tile>" in l]
        if len(tiles) != 16:
            fail(f"build emitted {len(tiles)} tiles, expected 16")
        else:
            ok(f"build emitted 16 tiles")
        if "<img>sheets/objects.png" not in text:
            fail("build did not point <img> at the sheet under textures/sheets/")
        else:
            ok("build points <img> at the author sheet")
        # Cell k -> crop (k%16)*16, 0 at scale 2; key k -> tileData first byte k.
        for k, t in enumerate(tiles):
            body = t.split(">", 1)[1]
            f = body.split(",")
            want_x = str((k % 16) * 16)
            want_data = f"{k:02X}{'00' * 15}"
            if f[0] != "0" or f[3] != want_x or f[4] != "0" or f[1].upper() != want_data:
                fail(f"tile {k} not re-pointed: {body}")
                break
        else:
            ok("tile crops re-pointed to sheet cells (scale 2, img 0)")
        audio = (folder / "audio" / "hires.txt").read_text(encoding="utf-8")
        if "<bgm>0,1,bgm/01.ogg" not in audio or "<sfx>0,3,sfx/03.ogg" not in audio:
            fail(f"audio manifest missing expected ids:\n{audio}")
        else:
            ok("audio manifest references the new OGGs with their file-name ids")
        # run(expect=0) above already asserted the lint gate (a non-zero lint
        # exit fails the build); "0 error(s)" in the text would false-match a
        # naive substring search, so rely on the exit code alone.
        ok("build lints clean (lint gate = exit 0)")

        # --- pack determinism + correctness ---
        rom = root / "syn.nes"
        subprocess.run([PY, str(GEN_ROM), str(rom)], check=True, capture_output=True)
        z1, z2 = root / "a.zip", root / "b.zip"
        run("pack", str(folder), "--rom", str(rom), "--name", "F5.4c Test", "--version", "1.0.0", "--out", str(z1))
        run("pack", str(folder), "--rom", str(rom), "--name", "F5.4c Test", "--version", "1.0.0", "--out", str(z2))
        d1, d2 = hashlib.sha256(z1.read_bytes()).hexdigest(), hashlib.sha256(z2.read_bytes()).hexdigest()
        if d1 != d2:
            fail(f"pack not deterministic: {d1} != {d2}")
        else:
            ok(f"pack is byte-deterministic ({d1[:12]}…)")
        with zipfile.ZipFile(z1) as zf:
            names = zf.namelist()
            if names[0] != "pack.json":
                fail(f"pack.json is not the first zip entry: {names[:3]}")
            else:
                ok("pack.json is the first zip entry")
            meta = zf.read("pack.json").decode("utf-8")
            pj = json_loads(meta)
        if pj.get("sections") != {"textures": {"path": "textures/"}, "audio": {"path": "audio/"}}:
            fail(f"pack.json sections wrong: {pj.get('sections')}")
        else:
            ok("pack.json sections derived from the tree")
        if not pj["targets"][0]["sha1"]:
            fail("pack --rom did not fill targets[0].sha1")
        else:
            ok(f"pack --rom computed No-Intro sha1 {pj['targets'][0]['sha1'][:8]}...")

        # --- rename-audio-id (F5.4g Bloco D item 12 id lifecycle) ---
        audio_dir = folder / "audio"
        (audio_dir / "midi").mkdir(exist_ok=True)
        (audio_dir / "midi" / "track01.mid").write_bytes(b"M")
        (audio_dir / "bgm" / "track01.ogg").write_bytes(b"O")
        fp = audio_dir / "fingerprints.json"
        fp.write_text('{\n  "version": 1,\n  "tracks": [\n'
                      '    { "id": "track01", "kind": "bgm", "frames": 10, "midi": "midi/track01.mid", "events": [[0,0,0]] }\n'
                      '  ]\n}\n', encoding="utf-8")
        (audio_dir / "hires.txt").write_text("<ver>107\n<bgm>0,1,bgm/track01.ogg\n", encoding="utf-8")
        run("rename-audio-id", str(folder), "track01", "track02")
        if not (audio_dir / "midi" / "track02.mid").exists() or (audio_dir / "midi" / "track01.mid").exists():
            fail("rename-audio-id did not move midi/track01.mid -> track02.mid")
        else:
            ok("rename-audio-id moved the midi file")
        if not (audio_dir / "bgm" / "track02.ogg").exists() or (audio_dir / "bgm" / "track01.ogg").exists():
            fail("rename-audio-id did not move bgm/track01.ogg -> track02.ogg")
        else:
            ok("rename-audio-id moved the bgm OGG")
        fp_text = fp.read_text(encoding="utf-8")
        if '"id": "track01"' in fp_text or '"midi": "midi/track01.mid"' in fp_text:
            fail("rename-audio-id did not rewrite fingerprints.json id/midi")
        else:
            ok("rename-audio-id rewrote fingerprints.json id + midi path")
        hires_text = (audio_dir / "hires.txt").read_text(encoding="utf-8")
        if "bgm/track01.ogg" in hires_text or "bgm/track02.ogg" not in hires_text:
            fail("rename-audio-id did not rewrite the audio/hires.txt reference")
        else:
            ok("rename-audio-id rewrote the audio/hires.txt reference")

        # --- flat-pack migration: dangling seed refs dropped, ids reclaimed ---
        mig = root / "migrate"
        (mig / "textures" / "sheets").mkdir(parents=True)
        (mig / "audio" / "bgm").mkdir(parents=True)
        (mig / "audio" / "sfx").mkdir(parents=True)
        (mig / "textures" / "sheets" / "a.png").write_bytes(png(256, 16))
        # Key source carries bgm/sfx whose files do NOT exist under audio/:
        # the migration path must drop them and hand the freed ids to the
        # real OGGs, not keep dangling refs or collide.
        (mig / "textures" / "hires.txt").write_text(
            "<ver>107\n<scale>2\n<system>nes\n"
            + "\n".join(f"<tile>0,{k:02X}{'00' * 15},0F001A2C,0,0,1,N" for k in range(16))
            + "\n<bgm>0,0,track01.ogg\n<sfx>0,3,jump.ogg\n", encoding="utf-8")
        (mig / "audio" / "bgm" / "01.ogg").write_bytes(b"")
        (mig / "audio" / "sfx" / "03.ogg").write_bytes(b"")
        run("build", str(mig))
        mig_audio = (mig / "audio" / "hires.txt").read_text(encoding="utf-8")
        if "track01.ogg" in mig_audio or "jump.ogg" in mig_audio:
            fail(f"migration kept dangling seed refs:\n{mig_audio}")
        elif "<bgm>0,1,bgm/01.ogg" not in mig_audio or "<sfx>0,3,sfx/03.ogg" not in mig_audio:
            fail(f"migration did not reclaim the freed ids:\n{mig_audio}")
        elif mig_audio.count("<sfx>") != 1 or mig_audio.count("<bgm>") != 1:
            fail(f"migration produced duplicate track ids:\n{mig_audio}")
        else:
            ok("flat-pack migration drops dangling refs, reclaims ids, no duplicates")

        # --- non-NES packs skip the audio manifest (frozen, ADR-0041) ---
        sms = root / "sms"
        (sms / "textures" / "sheets").mkdir(parents=True)
        (sms / "audio" / "bgm").mkdir(parents=True)
        (sms / "textures" / "sheets" / "a.png").write_bytes(png(256, 16))
        (sms / "textures" / "hires.txt").write_text(
            "<ver>200\n<system>sms\n<scale>2\n"
            + "\n".join(f"<tile>0,{k:02X}{'00' * 15},0F001A2C,0,0,1,N" for k in range(16))
            + "\n", encoding="utf-8")
        (sms / "audio" / "bgm" / "01.ogg").write_bytes(b"")
        out = run("build", str(sms))
        if (sms / "audio" / "hires.txt").exists():
            fail("non-NES build wrote an audio manifest (GB/SMS OGG frozen)")
        else:
            ok("non-NES build skips the audio manifest")

        # --- empty argv is a usage error, not a crash ---
        p = subprocess.run([PY, str(MEP_BUILD)], capture_output=True, text=True)
        if p.returncode != 2 or "usage" not in (p.stdout + p.stderr):
            fail(f"mep_build with no args -> exit {p.returncode}, expected 2 + usage")
        else:
            ok("mep_build with no args prints usage and exits 2")

        # --- failure modes (exit 2) ---
        no_source = root / "no-source"
        (no_source / "textures" / "sheets").mkdir(parents=True)
        (no_source / "textures" / "sheets" / "a.png").write_bytes(png(256, 16))
        out = run("build", str(no_source), expect=2)
        if out is not None and "no tile-key source" in out:
            ok("missing key source fails with guidance")
        else:
            fail(f"missing key source: {out}")

        small = make_author_folder(root, keys=20, name="small")  # 16 cells, 20 keys
        run("build", str(small), expect=2)

        wide = make_author_folder(root, name="wide")
        (wide / "textures" / "sheets" / "objects.png").unlink()
        (wide / "textures" / "sheets" / "objects.png").write_bytes(png(512, 16))  # 32 columns
        run("build", str(wide), expect=2)

        # --- ADR-0153 / F9.4: the artist-legible sheet round-trip ---
        sheet_alias_tests(root)
        sheet_round_trip_tests(root)

        # --- F5.4g item 12: audio_cleanup_suggest reads the probe's log ---
        sug = root / "sug-pack"
        (sug / "auto" / "audio").mkdir(parents=True)
        (sug / "auto" / "audio" / "enumeration.log").write_text(
            "id,kind,audible,frames,last,hash,first-notes,repeat\n"
            "0,bgm,300,300,299,37CEFCA2,\"s2 1\",no\n"
            "1,short,12,300,20,811C9DC5,\"s0 1\",no\n"
            "2,bgm,300,300,298,37CEFCA2,\"s2 1\",yes\n"
        )
        p = subprocess.run([PY, str(REPO / "scripts" / "audio_cleanup_suggest.py"), str(sug)],
                           capture_output=True, text=True)
        out = (p.stdout + p.stderr).strip()
        if p.returncode != 1 or "kind=short" not in out or "repeat of an earlier id" not in out:
            fail(f"audio_cleanup_suggest -> exit {p.returncode}, expected 1 + garbage ids: {out}")
        else:
            ok("audio_cleanup_suggest flags short/repeat/silent ids from the probe's enumeration.log")

    return 1 if FAILED else 0


def json_loads(s):
    import json
    return json.loads(s)


if __name__ == "__main__":
    sys.exit(main())
