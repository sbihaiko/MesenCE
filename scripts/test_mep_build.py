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
    rank as the tie-break when both, or neither, were painted;
  * PRD Phase 10 S10.c: `pack` carries the root `generated` label (MEP-v1
    §3.1 v1.6, ADR-0154 §3) across a rebuild, and the zip's membership is
    documented as it stands — every file under the folder, a non-pack
    `studio/` subfolder included;
  * PRD Phase 10 S10.d: coverage preservation for a repainted pack —
    `check-coverage` passes a fully skinned pack (pixels all differ) and
    fails a pack that lost a cell's tile keys or its sheet;
  * #172: `check-coverage` resolves candidate and baseline from one layout
    rule (the argument is the pack folder, as for `build`), says how to
    obtain a baseline when there is none, and refuses to compare the
    rebuilt manifest against itself;
  * #173: `build` reports its key count as a delta against the key source,
    says why dropping keys is the designed outcome and where the
    screen-owned cells are repainted, and groups the lint warnings about
    the tool's own sheet geometry instead of burying the rest.

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


# ADR-0172: a CHR ROM pack's sidecar carries each tile's CHR index next to its
# data. The fixture mints one per shape, far enough from 0 that a build reading
# the wrong field cannot land on the right token by accident.
CHR_INDEX_BASE = 0x40
EMIT_TILE_INDEX = False

# ADR-0178: the recorder bakes a sprite's OAM flips into the shape it records,
# so on a CHR RAM game the sidecar's `tile` is a key the run time never looks
# up and `source` carries the one it does. EMIT_FLIP_SOURCE writes both;
# EMIT_FLIP_BAKED writes the baked key alone, which is a pack recorded before
# the ADR.
EMIT_FLIP_SOURCE = False
EMIT_FLIP_BAKED = False


def flip_hex(data: str) -> str:
    """`data` read as if its OAM horizontal-flip bit had been baked in."""
    b = bytes.fromhex(data)
    return bytes(int(f"{x:08b}"[::-1], 2) for x in b).hex().upper()



def _tiles_json(tiles):
    parts = []
    for t in tiles:
        if t is None:
            parts.append("null")
            continue
        idx = f', "index": {CHR_INDEX_BASE + t}' if EMIT_TILE_INDEX else ""
        data = tile_hex(t)
        src = ""
        if EMIT_FLIP_SOURCE or EMIT_FLIP_BAKED:
            data, src = flip_hex(data), data
            src = f', "source": "{src}", "mirror": "H"' if EMIT_FLIP_SOURCE else ""
        parts.append(f'{{ "tile": "{data}", "palette": "{PAL_HEX}"{idx}{src} }}')
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


def make_sheet_folder(root: Path, name: str, scale: int = 1, chr_rom: bool = False,
                      sidecar_index: bool = True, flip_baked: bool = False,
                      sidecar_source: bool = True):
    """An ADR-0153 author folder: a metatile vocabulary of 6 cells, a stitched
    map over cells 0..3, and an object over cells 0..1.

    `chr_rom` writes the key source in the index form a CHR ROM game's
    manifest uses (ADR-0172); `sidecar_index` is what the sheet sidecars
    record, so the two can be set apart to reproduce a pack recorded before
    that ADR."""
    global EMIT_TILE_INDEX, EMIT_FLIP_SOURCE, EMIT_FLIP_BAKED
    EMIT_TILE_INDEX = chr_rom and sidecar_index
    # ADR-0178: `flip_baked` bakes a horizontal flip into every sidecar key;
    # `sidecar_source` decides whether the unflipped twin rides along, i.e.
    # whether the pack was recorded before or after the ADR.
    EMIT_FLIP_SOURCE = flip_baked and sidecar_source
    EMIT_FLIP_BAKED = flip_baked and not sidecar_source
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
        key = f"{CHR_INDEX_BASE + shape:02X}" if chr_rom else tile_hex(shape)
        lines.append(f"<tile>0,{key},{PAL_HEX},0,0,{extra}")
    (folder / "textures" / "hires.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    EMIT_TILE_INDEX = False
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


def screen_residency_tests(root: Path):
    """ADR-0156 (F9.9): the cells a captured screen owns leave `metatiles.png`,
    so the sidecar stops listing them and no sheet claims their tile keys any
    more. Two things have to hold for that to be safe: the build must not
    break, and the `<background>` line plus its PNG - the surface those cells
    were routed *to* - must come through the rebuild intact."""
    folder, vocab, cells = make_sheet_folder(root, "screen-resident")
    sheets = folder / "textures" / "sheets"
    unit, gutter, columns = 16, 1, 3

    # Cell 5 is the routed one: metatiles-only, so nothing else can claim its
    # keys. The builder would not have drawn it at all; dropping it from the
    # sidecar is the same thing as far as the slicing contract goes.
    kept = [c for c in cells if c["index"] != 5]
    (sheets / "metatiles.json").write_text(
        serialize_sheet("metatiles", unit, gutter, columns, "metatiles.png",
                        "metatiles.orig.png", kept),
        encoding="utf-8")

    # The screen the cell was routed to, as the emulator writes it: a
    # condition-gated <background> in the body, PNG under auto/textures only.
    hires = folder / "textures" / "hires.txt"
    bg_line = "[screen001_A&screen001_B]<background>backgrounds/screen001.png,1,0,0,20"
    hires.write_text(hires.read_text(encoding="utf-8") + bg_line + "\n", encoding="utf-8")
    auto_bg = folder / "auto" / "textures" / "backgrounds"
    auto_bg.mkdir(parents=True)
    (auto_bg / "screen001.png").write_bytes(png(256, 240))

    out = run("build", str(folder))
    if out is None:
        return
    _imgs, tiles = parse_hires(hires)
    routed = [s for s in (18, 19) if (tile_hex(s), PAL_HEX) in tiles]
    if routed:
        fail(f"a routed cell still claims tile keys {routed} after the rebuild")
    else:
        ok("ADR-0156: a cell routed to the screen surface claims no tile key")
    if (tile_hex(0), PAL_HEX) not in tiles:
        fail("routing one cell off metatiles.png took the rest of the sheet with it")
    else:
        ok("ADR-0156: the cells that stayed on the sheet still round-trip")
    body = [ln.strip() for ln in hires.read_text(encoding="utf-8").splitlines()]
    if bg_line not in body:
        fail("the <background> line the cells were routed to did not survive the rebuild")
    elif not (folder / "textures" / "backgrounds" / "screen001.png").is_file():
        fail("the captured screen was not copied up into textures/")
    else:
        ok("ADR-0156: the captured screen survives the rebuild, line and PNG")

    # Issue #170: a capture draws above every <tile>, so on the scenes it
    # covers the sheets are not the surface an artist paints. The build says so
    # - without it, repainting metatiles.png and seeing no change in game has
    # no explanation anywhere.
    if "captured screen(s)" not in out or "backgrounds/screen001.png" not in out:
        fail(f"the build does not name the captured screen as the surface to paint:\n{out}")
    else:
        ok("the build points at backgrounds/screen001.png as the surface that covers the scene")


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

    # --- the adjacency sidecar (ADR-0164 §2) is skipped silently ---
    # It is not a sheet: no cells[], no sheet PNG, nothing to slice - and a
    # warning on every pack would train users to ignore warnings.
    adj, _v, _c = make_sheet_folder(root, "sheets-adjacency")
    (adj / "textures" / "sheets" / "adjacency.json").write_text(
        '{"version": 1, "kind": "adjacency", "background": {"nodes": [], "edges": []}}',
        encoding="utf-8")
    out = run("build", str(adj))
    warned = "unknown sheet kind 'adjacency'" in out or "names sheet 'adjacency.png'" in out
    if out is not None and not warned and "metatiles.png" in out:
        ok("the adjacency sidecar is skipped silently and the build still slices the sheets")
    else:
        fail(f"adjacency sidecar: {out}")

    edited_precedence_tests(root)
    screen_residency_tests(root)
    chr_rom_key_tests(root)
    flip_baked_key_tests(root)


def flip_baked_key_tests(root: Path):
    """ADR-0178: a sprite shape is recorded with its OAM flips baked in, and on
    a CHR RAM game hires.txt keys by tile data — so the baked bitmap is a key
    nothing ever looks up and the rebuild has to emit the `source` the sidecar
    carries instead (issue #181)."""
    folder, _v, _c = make_sheet_folder(root, "flip-baked", flip_baked=True)
    out = run("build", str(folder))
    if out is None:
        return
    _imgs, tiles = parse_hires(folder / "textures" / "hires.txt")
    got = {k for k, _p in tiles}
    want = {tile_hex(s) for s in range(20)}
    if got == want:
        ok("ADR-0178: a flip-baked sidecar rebuilds with the unflipped keys the run time looks up")
    else:
        fail(f"flip-baked rebuild keys: missing {sorted(want - got)[:3]}, "
             f"unexpected {sorted(got - want)[:3]}")

    # A pack recorded before the ADR has no `source`. Its baked keys are
    # recognised by the un-flip test and the build fails rather than emitting
    # cells that would render nothing.
    legacy, _v, _c = make_sheet_folder(root, "flip-baked-legacy", flip_baked=True,
                                       sidecar_source=False)
    out = run("build", str(legacy), expect=2)
    if out is not None and "flip-baked tile key" in out and "re-record" in out:
        ok("ADR-0178: a pack whose sidecars predate the ADR fails the build, naming the fix")
    else:
        fail(f"pre-ADR-0178 pack did not fail with the re-record message: {out}")


def chr_rom_key_tests(root: Path):
    """ADR-0172: on a CHR ROM game hires.txt keys every tile by its CHR index,
    so the rebuild has to emit the index the sidecar records — emitting the
    32-hex data form instead produces a pack that loads, draws its captures and
    matches no tile at all (issue #170)."""
    folder, _v, _c = make_sheet_folder(root, "chr-rom", chr_rom=True)
    out = run("build", str(folder))
    if out is None:
        return
    _imgs, tiles = parse_hires(folder / "textures" / "hires.txt")
    want = {f"{CHR_INDEX_BASE + s:02X}" for s in range(20)}
    got = {k for k, _p in tiles}
    if got == want:
        ok("ADR-0172: a CHR ROM pack rebuilds with index keys, one per resolved crop")
    else:
        fail(f"CHR ROM rebuild keys: missing {sorted(want - got)}, unexpected {sorted(got - want)}")
    # The key source's own attributes must still reach the tile they belong to,
    # which only works when the carry-over lookup uses the index form too.
    entry = tiles.get((f"{CHR_INDEX_BASE:02X}", PAL_HEX))
    if entry and entry[3][5:] == ["0.5", "Y"]:
        ok("ADR-0172: brightness/defaultTile are carried over across the index form")
    else:
        fail(f"CHR ROM rebuild lost the key source's attributes: {entry}")

    # A pack recorded before the ADR has no index to emit. Failing loudly is
    # the decision: the alternative is a pack that silently renders nothing.
    legacy, _v, _c = make_sheet_folder(root, "chr-rom-legacy", chr_rom=True, sidecar_index=False)
    out = run("build", str(legacy), expect=2)
    if out is not None and "carry no tile index" in out and "re-record" in out:
        ok("ADR-0172: a CHR ROM pack whose sidecars predate the ADR fails the build, naming the fix")
    else:
        fail(f"pre-ADR-0172 CHR ROM pack did not fail with the re-record message: {out}")


def run(*argv, expect=0, cwd=None):
    p = subprocess.run([PY, str(MEP_BUILD), *argv], capture_output=True, text=True, cwd=cwd)
    out = (p.stdout + p.stderr).strip()
    if p.returncode != expect:
        fail(f"mep_build {' '.join(argv)} -> exit {p.returncode}, expected {expect}: {out}")
        return None
    return out


def chr_relegation_test(root: Path):
    """F9.10 (ADR-0160): the bootstrap writes its CHR-order fragments under
    `textures/chr/` and names them that way in `<img>`. The sheet build drops
    every `<img>` of the key source and re-emits its own, so where the
    fragments live must make no difference at all to the built manifest — and
    the built manifest must keep pointing only at `sheets/`, which is the whole
    point of relegating them."""
    old = make_author_folder(root, name="chr-at-root")
    new = make_author_folder(root, name="chr-in-subfolder")
    for folder, img in ((old, "<img>Chr_00_0.png"), (new, "<img>chr/Chr_00_0.png")):
        hires = folder / "textures" / "hires.txt"
        hires.write_text(hires.read_text(encoding="utf-8").replace("<img>old.png", img),
                         encoding="utf-8")
    if run("build", str(old)) is None or run("build", str(new)) is None:
        return
    old_text = (old / "textures" / "hires.txt").read_text(encoding="utf-8")
    new_text = (new / "textures" / "hires.txt").read_text(encoding="utf-8")
    if old_text != new_text:
        fail("moving the CHR-order fragments into chr/ changed the built hires.txt")
    elif [ln for ln in new_text.splitlines() if ln.startswith("<img>")] != ["<img>sheets/objects.png"]:
        fail(f"the built manifest does not reference sheets/ alone:\n{new_text}")
    else:
        ok("F9.10: a key source naming textures/chr/ builds the same manifest, pointing only at sheets/")


def pack_extra_data_tests(root: Path, rom: Path):
    """PRD Phase 10 S10.c: `pack` must carry the root `generated` object of an
    existing pack.json across the rebuild (MEP-v1 §3.1 v1.6, ADR-0154 §3 — the
    label is the disclosure, and losing it on export un-labels the pack), and
    the zip's membership is documented here as it stands: `folder.rglob("*")`
    ships every file under the folder, including a non-pack subfolder. Whether
    `pack` should exclude anything is a decision (an ADR), not a behaviour this
    test invents; what it pins is that the behaviour cannot change silently."""
    folder = make_author_folder(root, name="studio")
    if run("build", str(folder)) is None:
        return
    # A non-pack subfolder, the shape the skin studio would leave behind: a
    # transcript of the session plus a candidate image that never shipped.
    studio = folder / "studio"
    (studio / "candidates").mkdir(parents=True)
    (studio / "transcript.jsonl").write_text('{"turn": 1, "prompt": "chrome knight"}\n', encoding="utf-8")
    (studio / "candidates" / "skin.png").write_bytes(png(16, 16))
    generated = {"by": "sheet_repaint", "backend": "passthrough", "date": "2026-09-09",
                 "scale": 4, "source": "auto/textures/sheets"}
    (folder / "pack.json").write_text(json_dumps({
        "mep": "1.6.0", "name": "S10.c Test", "version": "0.1.0", "license": "CC0-1.0",
        "id": "probe-pack",
        "generated": generated,
        "targets": [{"system": "nes", "sha1": "2A4E126D0286BEA0BF503C80A12352C57539F76B"}],
        "sections": {"textures": {"path": "textures/"}},
    }), encoding="utf-8")

    z = root / "studio.zip"
    if run("pack", str(folder), "--rom", str(rom), "--out", str(z)) is None:
        return
    pj = json_loads((folder / "pack.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        zipped = json_loads(zf.read("pack.json").decode("utf-8"))
    if pj.get("generated") != generated:
        fail(f"pack rewrote pack.json without the root `generated` object: {pj.get('generated')}")
    elif zipped.get("generated") != generated:
        fail(f"the zipped pack.json lost the root `generated` object: {zipped.get('generated')}")
    else:
        ok("S10.c: pack carries the root `generated` object across a rebuild, on disk and in the zip")

    # `id` is the pack's product identity (MEP-v1 §3.1, ADR-0140 source (1)):
    # stable across revisions, and the catalog slot the pack competes for.
    # Dropping it on a re-pack sends the pack down the fallback chain, which
    # can move it to a different slot than its author declared.
    if pj.get("id") != "probe-pack" or zipped.get("id") != "probe-pack":
        fail(f"pack dropped the root `id`: on disk {pj.get('id')!r}, in the zip {zipped.get('id')!r}")
    else:
        ok("pack carries the root `id` across a rebuild, on disk and in the zip (ADR-0140)")

    want = ["pack.json", "audio/bgm/01.ogg", "audio/hires.txt", "audio/sfx/03.ogg",
            "studio/candidates/skin.png", "studio/transcript.jsonl",
            "textures/hires.txt", "textures/sheets/objects.png"]
    if names != want:
        fail(f"pack zip membership changed:\n  got  {names}\n  want {want}")
    else:
        ok("S10.c: pack zips every file under the folder — a non-pack studio/ subfolder ships with it")


def skin(folder: Path) -> int:
    """Repaint every sheet in place, leaving the `*.orig.png` twins alone: each
    pixel keeps its alpha and rotates its RGB channels, so all the art changes
    and no geometry does. That is what a skin tool returns, and why the
    pixel-exact identity round-trip cannot be its check (PRD Phase 10 S10.d)."""
    painted = 0
    for p in sorted((folder / "textures" / "sheets").glob("*.png")):
        if p.name.endswith(".orig.png"):
            continue
        px = png_read(p)
        for row in px:
            for i, v in enumerate(row):
                row[i] = (v & 0xFF000000) | ((v & 0x00FFFF) << 8) | ((v >> 16) & 0xFF)
        p.write_bytes(png_rgba(px))
        painted += 1
    return painted


def drop_cell(folder: Path, cells, index: int):
    """Rewrite metatiles.json without one cell — the way a repaint loses a
    subject: the sheet still builds, that cell's tile keys simply stop being
    claimed by anything (the ADR-0156 rewrite, used here as a defect)."""
    kept = [c for c in cells if c["index"] != index]
    (folder / "textures" / "sheets" / "metatiles.json").write_text(
        serialize_sheet("metatiles", 16, 1, 3, "metatiles.png", "metatiles.orig.png", kept),
        encoding="utf-8")


def coverage_preservation_tests(root: Path):
    """PRD Phase 10 S10.d: the "nothing broken" check for a repainted pack is
    key/coverage preservation, not pixel identity. Three arms: a skinned pack
    passes, a pack that lost a cell's keys fails naming them, and a pack whose
    sheet is gone fails as unresolved."""
    def baseline_of(folder: Path, name: str) -> Path:
        """The recorder's pack, kept aside before the repaint: its own manifest
        and its own PNGs, exactly what `--baseline` points at in practice."""
        copy = root / name
        shutil.copytree(folder, copy)
        return copy / "textures" / "hires.txt"

    # --- pass arm: every pixel repainted, every key kept ---
    good, _v, _c = make_sheet_folder(root, "skin-pass")
    if run("build", str(good)) is None:
        return
    base = baseline_of(good, "skin-pass-baseline")
    before = (good / "textures" / "sheets" / "metatiles.png").read_bytes()
    if skin(good) != 3 or (good / "textures" / "sheets" / "metatiles.png").read_bytes() == before:
        fail("the skin fixture did not actually change the sheet pixels")
        return
    if run("build", str(good)) is None:
        return
    out = run("check-coverage", str(good), "--baseline", str(base))
    if out is None:
        return
    if "every baseline tile key still resolves" not in out or "unchanged (19)" not in out:
        fail(f"S10.d: a fully repainted pack did not pass the coverage check:\n{out}")
    else:
        ok("S10.d: a skinned pack passes — every key resolves, tiles-with-art unchanged, pixels ignored")

    # --- fail arm: one cell dropped from the sidecar, its keys go with it ---
    bad, _v, bad_cells = make_sheet_folder(root, "skin-drop")
    if run("build", str(bad)) is None:
        return
    bad_base = baseline_of(bad, "skin-drop-baseline")
    skin(bad)
    drop_cell(bad, bad_cells, 5)  # metatile 5 is metatiles-only: shapes 18 and 19
    if run("build", str(bad)) is None:
        return
    out = run("check-coverage", str(bad), "--baseline", str(bad_base), expect=1)
    if out is None:
        return
    named = [tile_hex(s) for s in (18, 19) if f"{tile_hex(s)}/{PAL_HEX}" in out]
    if "2 baseline tile key(s) no longer resolve" not in out:
        fail(f"S10.d: a dropped cell did not fail as a dropped key:\n{out}")
    elif len(named) != 2:
        fail(f"S10.d: the failure did not name both dropped keys ({named}):\n{out}")
    elif "tiles-with-art count changed over the baseline's keys: 19 -> 17" not in out:
        fail(f"S10.d: the failure did not report the F5.4d count loss:\n{out}")
    else:
        ok("S10.d: a pack with a dropped key fails, naming the keys and the tiles-with-art loss")

    # --- fail arm: the keys are still declared, but their sheet is gone ---
    gone, _v, _c = make_sheet_folder(root, "skin-gone")
    if run("build", str(gone)) is None:
        return
    gone_base = baseline_of(gone, "skin-gone-baseline")
    skin(gone)
    if run("build", str(gone)) is None:
        return
    (gone / "textures" / "sheets" / "metatiles.png").unlink()
    out = run("check-coverage", str(gone), "--baseline", str(gone_base), expect=1)
    if out is None:
        return
    if "is missing or not a valid PNG" not in out:
        fail(f"S10.d: a missing sheet was not reported as an unresolved key:\n{out}")
    else:
        ok("S10.d: a key whose sheet is missing fails as unresolved, not as a pass")


def check_coverage_layout_tests(root: Path):
    """#172: `check-coverage` resolves both of its paths from one rule — the
    argument is the pack folder, exactly the one `build` takes — and it never
    compares the rebuilt manifest against itself.

    Three arms: the documented layout (the recorder's pack kept nested under
    `auto/`, which is also `build`'s second key source) runs with no
    `--baseline` at all; a pack with no baseline anywhere says how to obtain
    one instead of telling the user to run a `build` they have just run; and a
    `--baseline` that resolves to the candidate is refused rather than passed
    vacuously, which is the guard the F9.18 panel never actually got."""
    pack, _v, _c = make_sheet_folder(root, "cc-layout")
    if run("build", str(pack)) is None:
        return
    # The recorder's manifest and its sheets, kept nested where `build` writing
    # in place cannot reach them.
    shutil.copytree(pack / "textures", pack / "auto" / "textures")
    if run("build", str(pack)) is None:
        return
    out = run("check-coverage", str(pack))
    if out is None:
        return
    if "every baseline tile key still resolves" not in out:
        fail(f"#172: check-coverage on the pack folder did not run against its default baseline:\n{out}")
    else:
        ok("#172: check-coverage takes the pack folder and finds its default baseline there")

    # No baseline anywhere: `build` has run, so "run build first" is advice
    # about a step already taken and names a file that is not the missing one.
    lone, _v, _c = make_sheet_folder(root, "cc-nobaseline")
    if run("build", str(lone)) is None:
        return
    out = run("check-coverage", str(lone), expect=2)
    if out is None:
        return
    if "run `mep_build.py build` first" in out or "before `build` ran" not in out:
        fail(f"#172: the missing-baseline error does not say how to obtain a baseline:\n{out}")
    else:
        ok("#172: a missing baseline says how to obtain one, not `run build first`")

    out = run("check-coverage", str(lone), "--baseline",
              str(lone / "textures" / "hires.txt"), expect=2)
    if out is None:
        return
    if "same file" not in out:
        fail(f"#172: comparing the rebuilt manifest with itself was not refused:\n{out}")
    else:
        ok("#172: baseline == candidate is refused instead of passing vacuously")


def build_summary_tests(root: Path):
    """#173: the build summary must let an artist tell designed narrowing from
    a broken rebuild.

    A rebuild legitimately carries fewer keys than the manifest it read: the
    bootstrap exports every CHR tile as a palette-agnostic defaultTile
    (ADR-0043), the sheets carry only what was routed to them, and the cells a
    captured screen owns are off the sheets entirely (ADR-0156/ADR-0160) —
    ADR-0172 measured that shape and accepted it. So the count is reported as a
    delta against the key source, with the reason, and the lint warnings about
    the tool's own sheet geometry are grouped instead of burying the lines an
    artist can act on."""
    folder, _v, _c = make_sheet_folder(root, "summary")
    # Four keys no sheet carries — the shape of a key the recorder exported and
    # the rebuild cannot route, e.g. a cell a captured screen owns.
    hires = folder / "textures" / "hires.txt"
    hires.write_text(hires.read_text(encoding="utf-8")
                     + "".join(f"<tile>0,{tile_hex(s)},{PAL_HEX},0,0,1,N\n" for s in range(40, 44)),
                     encoding="utf-8")
    out = run("build", str(folder))
    if out is None:
        return
    if "tile keys: 12 in the key source" not in out or "8 carried, 4 dropped" not in out:
        fail(f"#173: build did not report the key count as a delta against its key source:\n{out}")
    else:
        ok("#173: build reports tile keys as a delta against the manifest it read")
    if "expected, not breakage" not in out or "backgrounds/screenNNN.png" not in out:
        fail(f"#173: dropped keys came with no reason and no repaint surface named:\n{out}")
    else:
        ok("#173: a dropped key is explained, with the screen-owned case named")
    if "not a multiple of" in out:
        fail(f"#173: the tool's own sheet-geometry warnings are still inline:\n{out}")
    elif "are about the tool's own output" not in out or "sheets/metatiles.png" not in out:
        fail(f"#173: the tool's own warnings were silenced instead of grouped and named:\n{out}")
    else:
        ok("#173: the tool's own sheet-geometry warnings are grouped, counted and named")


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
    lines.extend(f"<tile>0,{k:02X}{'00' * 15},0F001A2C,0,0,1,N" for k in range(keys))
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
        tiles = [ln for ln in text.splitlines() if "<tile>" in ln]
        if len(tiles) != 16:
            fail(f"build emitted {len(tiles)} tiles, expected 16")
        else:
            ok("build emitted 16 tiles")
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

        # --- F9.10: sheets/ is the front door; chr/ is where the CHR-order
        # fragments went, and the round trip cannot notice the difference ---
        chr_relegation_test(root)

        # --- PRD Phase 10 S10.c/S10.d: the export label + local data, and
        # the coverage rule that replaces pixel identity for a skinned pack ---
        pack_extra_data_tests(root, rom)
        coverage_preservation_tests(root)

        # --- #172 / #173: the two reporting defects the Phase 9 validation
        # panel hit — a coverage check that could not be pointed anywhere, and
        # a build summary that read as damage ---
        check_coverage_layout_tests(root)
        build_summary_tests(root)

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


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj, indent=2) + "\n"


if __name__ == "__main__":
    sys.exit(main())
