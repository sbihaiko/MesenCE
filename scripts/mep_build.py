#!/usr/bin/env python3
"""mep_build — author-side MEP pack builder (PRD F5.4c, ADR-0049 §2).

Builds the generated manifests of an HD/MEP pack project folder from its
editable source material, then packages it into a MEP zip:

    scripts/mep_build.py build <folder> [--scale N] [--source PATH] [--quiet]
    scripts/mep_build.py pack  <folder> [--out ZIP] [--rom ROM |
        --system S --sha1 H] [--name N] [--version V] [--author A]
        [--license L] [--quiet]
    scripts/mep_build.py rename-audio-id <folder> <old-id> <new-id>
    scripts/mep_build.py <folder>            # same as `build`

build  reads `textures/sheets/*.png` (16-column grids of `8*scale`-px
       cells; ADR-0049: cells map to tile keys through the sheet's order),
       regenerates `textures/hires.txt` pointing every tile key at the cell
       that owns it, regenerates `audio/hires.txt` from the OGGs under
       `audio/bgm/` and `audio/sfx/` (new files pick up the same track/sfx
       id as their file name, or the next free id), writes a comment header
       recording the cell -> key map, and runs the MEP linter over the
       result. The linter failing is a build failure.

       Tile keys are NOT derivable from art (an upscaled cell carries no
       2bpp pattern or NES palette index), so the keys come from a key
       source: `--source`, else `textures/hires.txt` (a prior build), else
       `auto/textures/hires.txt` (the emulator bootstrap, F5.2). The sheets
       replace the art; the keys and the header tags (ver/scale/system/
       supportedRom/options/overscan) are carried over. Background tags are
       preserved; a background PNG missing under `textures/` but present
       under `auto/textures/` is copied up (the author keeps their assets).
       <bgm>/<sfx> never live in the textures manifest — they belong to the
       audio section (MEP-v1 §2.1 rule 6), so build moves them there.

       ADR-0153 sheets (F9.4) live in the same folder and are recognised by
       their sidecar: `textures/sheets/<name>.json` with `"version": 1`. They
       are NOT 16-column grids — each cell carries the exact hires.txt key of
       every 8x8 tile inside it, so the build slices them back through
       `cells[]` (contact sheets) or `placements[]` (a stitched map, resolved
       against the sibling `metatiles.json` vocabulary) and emits one <tile>
       per resolved crop. `*.orig.png` twins are references: never sliced,
       never emitted. An artist can therefore paint a sheet in any image
       editor, re-run build, and see the change in the emulator without ever
       opening hires.txt.

       The same tile key comes out of several sheets (a metatile is also on
       the map, and inside an object), so a cell only *claims* a key when it
       was actually painted, measured against its `*.orig.png` twin. Painted
       beats untouched; among painted cells - and among untouched ones - the
       static kind rank decides.

pack   writes `pack.json` at the folder root from the folder tree and the
       given identity (MEP-v1 §3.1), then zips the whole folder with a
       deterministic layout (fixed timestamps, STORED, 0o644, lexical
       order) so a rebuilt zip is byte-identical — the F6.4c fixture
       pattern. `targets` come from `--rom` (No-Intro sha1), explicit
       `--system/--sha1`, or an existing `pack.json`. The zip is linted too.

rename-audio-id  renames an enumerated `trackNN`/`sfxNN` audio id across
       `audio/fingerprints.json` (the `id` and `midi` fields), the physical
       `midi/`/`bgm/`/`sfx/` files, and any `audio/hires.txt` reference —
       the F5.4g Bloco D item 12 id-lifecycle cleanup.

Exit codes mirror mep_lint: 0 = clean, 1 = errors found, 2 = usage error.
"""

import argparse
import hashlib
import json
import re
import struct
import sys
import zipfile
import zlib
from pathlib import Path

import mep_lint

# NES hires.txt version emitted for the texture and audio manifests (ver >=
# 100 is the current HD format; 107 is what HdPackBuilder::SaveHdPack writes).
NES_VER = "107"
# Header tags carried over verbatim from the key source.
_HEADER_TAGS = ("ver", "scale", "system", "supportedRom", "options", "overscan")
_TILE_RE = re.compile(r"^(\[[^\]]*\])?<tile>(.*)$")
_BGM_RE = re.compile(r"^(\[[^\]]*\])?<bgm>(.*)$")
_SFX_RE = re.compile(r"^(\[[^\]]*\])?<sfx>(.*)$")
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)


class BuildError(Exception):
    pass


def _png_size(path: Path):
    """(width, height) from a PNG IHDR, or None when the file is not a PNG.
    Reads only the 24-byte header, so no image library is required."""
    try:
        data = path.read_bytes()[:24]
    except OSError:
        return None
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def _parse_source(lines):
    """Splits a hires.txt into header tags, ordered tile lines (condition
    prefix + raw fields), audio references (<bgm>/<sfx>), and the remaining
    body (backgrounds, patches, ...). <img> lines are dropped — the sheet
    build regenerates them."""
    header = []
    tiles = []
    audio_refs = []
    body = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("<") and s[1:].split(">", 1)[0] in _HEADER_TAGS:
            header.append(s)
            continue
        m = _TILE_RE.match(s)
        if m:
            tiles.append((m.group(1) or "", m.group(2)))
            continue
        if _BGM_RE.match(s) or _SFX_RE.match(s):
            audio_refs.append(s)
            continue
        if s.startswith("<img>"):
            continue
        body.append(s)
    return header, tiles, audio_refs, body


def _sheet_layout(path: Path, scale: int) -> int:
    """Cell count for a sheet: a 16-column grid of `8*scale` cells. Raises
    when the PNG is missing/invalid or not 16 columns (the fixed HD sheet
    geometry, HdPackBuilder::SaveHdPack)."""
    size = _png_size(path)
    if size is None:
        raise BuildError(f"{path.name}: not a valid PNG")
    cell = 8 * scale
    width, height = size
    if width % cell or height % cell:
        raise BuildError(f"{path.name}: {width}x{height} is not a multiple of {cell} (scale {scale})")
    cols = width // cell
    if cols != 16:
        raise BuildError(f"{path.name}: {width}px wide = {cols} columns, expected 16 (8*scale per cell)")
    return cols * (height // cell)


# --- ADR-0153 (F9.4): artist-legible sheets --------------------------------
#
# Precedence when two sheets resolve the same hires.txt tile key.
#
# The first question is not "which kind of sheet?" but "which sheet did the
# artist edit?", because hires.txt keys by tile content: the same key comes
# out of metatiles.png, out of the map that places that metatile, and out of
# any object built from it. A cell claims a key only when its pixels differ
# from the `*.orig.png` twin (see _EditedProbe), so PRD Phase 9 validation
# test 3 (paint a bush on metatiles.png) and test 4 (paint a seam on
# map-NNN.png) both work - no static order can satisfy both.
#
# The rank below is the tie-break, applied among painted cells and, when
# nobody painted anything, among untouched ones (the captured art still has
# to reach hires.txt, or the identity round-trip breaks). It reads "most
# specific last": the metatile vocabulary is the generic building block, a
# map is the surface the artist actually paints, an object/sprite is a named
# figure, and a HUD/font glyph is the most specific thing a tile can be. A
# legacy (ADR-0049, 16-column) sheet always loses to an ADR-0153 sheet. Ties
# inside one rank are broken by sidecar file name, later wins. Every override
# is logged, so a surprising win is visible in the build output rather than
# silent.
_SHEET_RANK = {
    "metatiles": 1,
    "misc": 2,
    "map": 3,
    "object": 4,
    "sprite": 4,
    "hud": 5,
    "font": 5,
}
_SHEET_VERSION = 1
_HEX_TILE_RE = re.compile(r"^[0-9A-F]{32}$")
_HEX_PAL_RE = re.compile(r"^[0-9A-F]{8}$")


class SheetDoc:
    """One ADR-0153 sidecar plus the PNG it names."""

    def __init__(self, json_path: Path, png_path: Path, doc: dict):
        self.json_path = json_path
        self.png_path = png_path
        self.doc = doc
        self.kind = str(doc.get("kind") or "")
        self.unit = int(doc.get("gridUnit") or 8)
        self.gutter = int(doc.get("gutter") or 0)
        self.columns = max(1, int(doc.get("columns") or 1))
        self.cells = doc.get("cells") or []
        self.rank = _SHEET_RANK[self.kind]

    @property
    def name(self) -> str:
        return self.png_path.name

    @property
    def tiles_per_cell(self) -> int:
        # SheetRender::AppendTiles emits 4 entries at grid unit 16 (row-major
        # 2x2) and 1 at unit 8.
        return 4 if self.unit >= 16 else 1


def _is_reference_png(path: Path) -> bool:
    """`*.orig.png` is the F5.4d pixel-exact twin: a reference for the artist,
    never a build input (ADR-0153 §3)."""
    return path.name.lower().endswith(".orig.png")


def _load_sheet_docs(sheets_dir: Path):
    """Every `<name>.json` under textures/sheets/ that declares version 1.
    Anything else is skipped with a warning — never a crash (F9.4 req. 1).

    Returns (docs, claimed): a PNG that any sidecar points at is claimed even
    when that sidecar is unusable, so an ADR-0153 sheet is never mistaken for
    an ADR-0049 16-column grid and blamed for the wrong geometry."""
    docs = []
    claimed = set()
    for jp in sorted(sheets_dir.glob("*.json")):
        claimed.add(sheets_dir / f"{jp.stem}.png")
        try:
            doc = json.loads(jp.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"warning: {jp.name}: not readable as JSON, skipped ({e})")
            continue
        if not isinstance(doc, dict):
            print(f"warning: {jp.name}: sidecar is not a JSON object, skipped")
            continue
        version = doc.get("version")
        if version != _SHEET_VERSION:
            print(f"warning: {jp.name}: sheet version {version!r} is not {_SHEET_VERSION}, skipped "
                  "(this build only knows the ADR-0153 v1 schema)")
            continue
        kind = str(doc.get("kind") or "")
        if kind not in _SHEET_RANK:
            print(f"warning: {jp.name}: unknown sheet kind {kind!r}, skipped")
            continue
        png = sheets_dir / str(doc.get("sheet") or f"{jp.stem}.png")
        claimed.add(png)
        if not png.is_file():
            print(f"warning: {jp.name}: names sheet '{png.name}', which does not exist — skipped")
            continue
        if _is_reference_png(png):
            print(f"warning: {jp.name}: names the reference twin '{png.name}' — skipped")
            continue
        docs.append(SheetDoc(jp, png, doc))
    return docs, claimed


def _logical_size(sd: SheetDoc):
    """The size SheetRender emitted the contact sheet at, before any upscale.
    Width comes from `columns` (exact even when the last row is short) and
    height from the lowest cell — both mirror BuildContactSheet/RenderGroup."""
    stride = sd.unit + sd.gutter
    width = sd.columns * stride + sd.gutter
    bottom = 0
    for c in sd.cells:
        try:
            bottom = max(bottom, int(c.get("y", 0)))
        except (TypeError, ValueError):
            continue
    return width, bottom + sd.unit + sd.gutter


def _sheet_scale(docs: list) -> int | None:
    """Integer upscale factor N shared by the ADR-0153 contact sheets: an
    artist may paint at 1x or at any integer multiple of what the builder
    emitted. A non-integer ratio, or two sheets at different factors, is a
    build error. Maps carry no `columns`, so they inherit N and are bounds
    checked while slicing. Returns None when nothing pins N down."""
    found = None
    origin = None
    for sd in docs:
        if sd.kind == "map" or not sd.cells:
            continue
        size = _png_size(sd.png_path)
        if size is None:
            raise BuildError(f"{sd.name}: not a valid PNG")
        lw, lh = _logical_size(sd)
        if lw <= 0 or lh <= 0:
            continue
        w, h = size
        if w % lw or h % lh or w // lw != h // lh or w // lw < 1:
            raise BuildError(
                f"{sd.name}: {w}x{h} is not an integer multiple of the {lw}x{lh} sheet "
                f"{sd.json_path.name} describes — resize by a whole factor (1x, 2x, 3x, ...)")
        n = w // lw
        if found is None:
            found, origin = n, sd.name
        elif n != found:
            raise BuildError(
                f"{sd.name}: painted at {n}x while {origin} is at {found}x — "
                "all sheets of a pack share one <scale>")
    return found


def _vocabulary(sd: SheetDoc, sheets_dir: Path):
    """The metatile vocabulary a map's `placements[].cell` indexes into: the
    `cells[]` of the sibling metatiles.json (ADR-0153 §4/§6). Cells are keyed
    by their `metatile` (the vocabulary index the builder wrote) and, as a
    fallback, by their position in the array."""
    meta = sheets_dir / "metatiles.json"
    if not meta.is_file():
        print(f"warning: {sd.json_path.name}: no sibling metatiles.json to resolve placements against — sheet skipped")
        return None
    try:
        doc = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"warning: metatiles.json is not readable ({e}) — {sd.json_path.name} skipped")
        return None
    cells = doc.get("cells") if isinstance(doc, dict) else None
    if not isinstance(cells, list) or not cells:
        print(f"warning: metatiles.json has no cells[] — {sd.json_path.name} skipped")
        return None
    by_index = {}
    for pos, c in enumerate(cells):
        if not isinstance(c, dict):
            continue
        by_index.setdefault(pos, c)
    by_vocab = {}
    for c in cells:
        if isinstance(c, dict) and isinstance(c.get("metatile"), int):
            by_vocab.setdefault(c["metatile"], c)
    return by_vocab or by_index, by_index


class _Bitmap:
    """Unfiltered 8-bit RGB/RGBA scanlines of a PNG, kept as raw bytes: the
    edited-cell test compares byte ranges, never per-pixel Python objects, so
    a 4096px-wide map stays cheap."""

    def __init__(self, width: int, height: int, channels: int, raw: bytearray):
        self.width = width
        self.height = height
        self.channels = channels
        self.raw = raw
        self.stride = width * channels
        self._rows = {}

    def band(self, y: int, x0: int, x1: int) -> bytes:
        off = y * self.stride
        return bytes(self.raw[off + x0 * self.channels:off + x1 * self.channels])

    def band_upscaled(self, y: int, x0: int, x1: int, n: int) -> bytes:
        """`band` with every pixel repeated n times — the reference twin as it
        would look painted at n x, without materialising the whole image."""
        if n == 1:
            return self.band(y, x0, x1)
        key = (y, x0, x1, n)
        got = self._rows.get(key)
        if got is None:
            src = self.band(y, x0, x1)
            ch = self.channels
            got = b"".join(src[i:i + ch] * n for i in range(0, len(src), ch))
            self._rows[key] = got
        return got


def _png_pixels(path: Path):
    """Decode a non-interlaced 8-bit RGB/RGBA PNG into a _Bitmap, or None when
    the file is missing or in a form this builder cannot read (16-bit, palette,
    interlaced). None means "cannot compare", which the caller turns into
    "treat the sheet as edited" — never into a wrong slice."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 8 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos = 8
    width = height = channels = 0
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            if length < 13:
                return None
            width, height, depth, color, _comp, _filt, interlace = struct.unpack(">IIBBBBB", body[:13])
            if depth != 8 or interlace != 0 or color not in (2, 6):
                return None
            channels = 3 if color == 2 else 4
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
        pos += 12 + length
    if not width or not height or not channels:
        return None
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None
    stride = width * channels
    if len(raw) < height * (stride + 1):
        return None
    out = bytearray(height * stride)
    prev = bytes(stride)
    bpp = channels
    src = 0
    for y in range(height):
        ft = raw[src]
        src += 1
        line = bytearray(raw[src:src + stride])
        src += stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 0xFF
        elif ft != 0:
            return None
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return _Bitmap(width, height, channels, out)


class _EditedProbe:
    """Answers "was this cell painted?" for one sheet, by comparing it with its
    pixel-exact `*.orig.png` twin (ADR-0153 §3, F5.4d `_writeReferences`).

    The twin is always 1x while the sheet may be painted at N x, so the sheet
    is compared against the twin upscaled by N — the cheaper direction, since
    it needs no resampling decision and no whole-image allocation.

    With no usable twin (`"reference": ""`, a missing or unreadable file, a
    size that is not exactly N x the sheet's) there is nothing to diff against,
    so every cell of that sheet counts as edited and the static rank decides,
    exactly as before this rule existed."""

    def __init__(self, sd: "SheetDoc", scale: int, sheets_dir: Path):
        self.scale = scale
        self.sheet = None
        self.orig = None
        self.reason = ""
        ref = str(sd.doc.get("reference") or "").strip()
        if not ref:
            self.reason = "no reference twin declared"
            return
        ref_path = sheets_dir / ref
        if not ref_path.is_file():
            self.reason = f"reference twin {ref} does not exist"
            return
        self.sheet = _png_pixels(sd.png_path)
        self.orig = _png_pixels(ref_path)
        if self.sheet is None or self.orig is None:
            self.reason = f"{sd.name} or {ref} is not an 8-bit RGB/RGBA PNG"
            self.sheet = self.orig = None
        elif (self.orig.width * scale != self.sheet.width
              or self.orig.height * scale != self.sheet.height
              or self.orig.channels != self.sheet.channels):
            self.reason = (f"reference twin {ref} is {self.orig.width}x{self.orig.height}, "
                           f"not {self.sheet.width // scale}x{self.sheet.height // scale}")
            self.sheet = self.orig = None

    @property
    def blind(self) -> bool:
        return self.sheet is None or self.orig is None

    def edited(self, ox: int, oy: int, size: int) -> bool:
        """True when the `size`x`size` cell at logical (ox, oy) differs from
        the twin. Granularity is the cell, not the 8x8 tile: an artist repaints
        a bush, not a quadrant of one."""
        if self.blind:
            return True
        n = self.scale
        px0, py0, span = ox * n, oy * n, size * n
        if px0 < 0 or py0 < 0 or px0 + span > self.sheet.width or py0 + span > self.sheet.height:
            return True
        for py in range(py0, py0 + span):
            if self.sheet.band(py, px0, px0 + span) != self.orig.band_upscaled(py // n, ox, ox + size, n):
                return True
        return False


def _cell_crops(tiles, ox: int, oy: int, per_cell: int, scale: int, where: str, out: list, skipped: list,
                edited: bool = True):
    """One 8x8 crop per resolved entry of `tiles[]`, row-major inside the cell
    at the same offsets RenderMetatile drew them. A null/short/malformed entry
    means that sub-tile had no art: it is skipped, and the entries after it do
    NOT shift up (F9.4 req. 2)."""
    if not isinstance(tiles, list):
        skipped.append(where)
        return
    for i in range(per_cell):
        entry = tiles[i] if i < len(tiles) else None
        if not isinstance(entry, dict):
            skipped.append(f"{where}[{i}]")
            continue
        data = str(entry.get("tile") or "").strip().upper()
        pal = str(entry.get("palette") or "").strip().upper()
        if not _HEX_TILE_RE.match(data) or not _HEX_PAL_RE.match(pal):
            skipped.append(f"{where}[{i}]")
            continue
        out.append(((ox + (i % 2) * 8) * scale, (oy + (i // 2) * 8) * scale, data, pal, edited))


def _slice_sheet(sd: SheetDoc, scale: int, sheets_dir: Path) -> list:
    """(x, y, tileData, palette, edited) for every 8x8 crop the sheet resolves,
    in sheet pixels at `scale`. `edited` says the crop's cell differs from the
    `*.orig.png` twin, i.e. the artist actually painted it. Crops that fall
    outside the PNG are dropped with a warning rather than emitting a tile that
    would render transparent."""
    crops = []
    skipped = []
    per = sd.tiles_per_cell
    probe = _EditedProbe(sd, scale, sheets_dir)
    if probe.blind:
        print(f"info: {sd.name}: {probe.reason} — every cell counts as painted (static precedence applies)")
    if sd.kind == "map":
        vocab = _vocabulary(sd, sheets_dir)
        if vocab is None:
            return []
        by_vocab, by_pos = vocab
        unresolved = 0
        for p in sd.doc.get("placements") or []:
            if not isinstance(p, dict):
                unresolved += 1
                continue
            try:
                px, py, idx = int(p["x"]), int(p["y"]), int(p["cell"])
            except (KeyError, TypeError, ValueError):
                unresolved += 1
                continue
            cell = by_vocab.get(idx, by_pos.get(idx))
            if cell is None:
                unresolved += 1
                continue
            _cell_crops(cell.get("tiles"), px, py, per, scale, f"{sd.name} @({px},{py})", crops, skipped,
                        probe.edited(px, py, sd.unit))
        if unresolved:
            print(f"warning: {sd.name}: {unresolved} placement(s) do not resolve in the metatile vocabulary — skipped")
    else:
        for c in sd.cells:
            if not isinstance(c, dict):
                skipped.append(sd.name)
                continue
            try:
                cx, cy = int(c["x"]), int(c["y"])
            except (KeyError, TypeError, ValueError):
                skipped.append(sd.name)
                continue
            painted = probe.edited(cx, cy, sd.unit)
            _cell_crops(c.get("tiles"), cx, cy, per, scale, f"{sd.name} cell {c.get('index')}", crops, skipped,
                        painted)
            # ADR-0153 §3 alias pass (F9.7): a bank-swapping mapper delivers the
            # same drawing under several tile keys, so the sheet carries one cell
            # per *subject* and lists the keys it absorbed. The artist paints the
            # crop once and every alias is emitted from it — which is also the
            # only way the duplicates cannot drift apart, as they did when each
            # was painted by hand.
            for alias in c.get("aliases") or []:
                if not isinstance(alias, dict):
                    continue
                _cell_crops(alias.get("tiles"), cx, cy, per, scale,
                            f"{sd.name} cell {c.get('index')} alias {alias.get('metatile')}",
                            crops, skipped, painted)
    if skipped:
        print(f"info: {sd.name}: {len(skipped)} sub-tile(s) with no art skipped (null/short tiles[])")

    size = _png_size(sd.png_path)
    if size is None:
        raise BuildError(f"{sd.name}: not a valid PNG")
    w, h = size
    span = 8 * scale
    inside = [c for c in crops if 0 <= c[0] and 0 <= c[1] and c[0] + span <= w and c[1] + span <= h]
    if len(inside) != len(crops):
        print(f"warning: {sd.name}: {len(crops) - len(inside)} crop(s) fall outside the {w}x{h} image — dropped")
    return inside


def _emit_comment(sheet_rel: str, cell: int) -> list:
    """ADR-0049: the generated hires.txt records the cell -> key map in a
    comment header, so the mapping survives edits and re-builds."""
    return [
        f"# {sheet_rel} — {cell} cell(s); cells map to tile keys through the sheet's order (ADR-0049)",
    ]


def _emit_sheet_comment(sheet_rel: str, kind: str, tiles: int, sidecar: str) -> list:
    """ADR-0153 §4: the sidecar is the slicing contract, so the generated
    manifest points at it instead of restating the cell -> key map."""
    return [
        f"# {sheet_rel} — {kind} sheet, {tiles} tile crop(s) sliced through {sidecar} (ADR-0153)",
    ]


def _bgm_sfx_refs(lines):
    """Files already referenced by <bgm>/<sfx> as (kind, stem) -> (album,
    track, filename)."""
    known = {}
    for s in lines:
        for rx, kind in ((_BGM_RE, "bgm"), (_SFX_RE, "sfx")):
            m = rx.match(s)
            if not m:
                continue
            fields = [f.strip() for f in m.group(2).split(",")]
            if len(fields) >= 3:
                known[(kind, Path(fields[2]).stem)] = (fields[0], fields[1], fields[2])
    return known


def _next_free_id(ids, start=1):
    n = start
    while n in ids:
        n += 1
    return n


def _build_audio_manifest(folder: Path, system: str | None, seed: list) -> str | None:
    """Regenerates audio/hires.txt from `seed` (previous manifest or the key
    source's own <bgm>/<sfx>) plus the OGGs under audio/bgm/ and audio/sfx/
    that are not referenced yet.

    NES-only: GB/SMS/GG OGG replacement is frozen (ADR-0041) and mep_lint has
    no audio tags for the ver>=200 format, so a non-NES pack returns None.
    Seed refs whose OGG no longer exists are dropped (their track id is
    reclaimed); a digit-named OGG's id is honoured only when free, else the
    next free id is used — so the manifest never carries two <bgm>/<sfx>
    entries with the same album*256+track id.

    Returns the manifest text, or None when there is nothing to reference."""
    if system is not None and system != "nes":
        return None
    # Keep only seed refs whose OGG actually exists in the audio/ layout; a
    # dangling ref would ship an unregistered track (lint warning) and its id
    # must be reclaimed, not held.
    keep = []
    for s in seed:
        for rx, kind in ((_BGM_RE, "bgm"), (_SFX_RE, "sfx")):
            m = rx.match(s)
            if not m:
                continue
            fields = [f.strip() for f in m.group(2).split(",")]
            if len(fields) >= 3 and (folder / "audio" / Path(fields[2])).exists():
                keep.append(s)
            else:
                print(f"info: dropping {kind} ref {fields[2]} (no such file under audio/)")
            break
    kept_refs = _bgm_sfx_refs(keep)

    def scan(sub: str, kind: str):
        entries = []
        known = dict(kept_refs)
        used_ids = {int(t) for (k, _), (a, t, _) in known.items() if k == kind and a == "0" and t.isdigit()}
        d = folder / "audio" / sub
        if not d.is_dir():
            return entries
        for f in sorted(d.glob("*.ogg")):
            stem = f.stem
            if (kind, stem) in known:
                continue  # already referenced
            album = 0
            if stem.isdigit():
                track = int(stem)
                if track in used_ids:
                    print(f"info: {kind} id {track} already taken — using next free id for {f.name}")
                    track = _next_free_id(used_ids)
            else:
                track = _next_free_id(used_ids)
            used_ids.add(track)
            entries.append(f"<{kind}>{album},{track},{sub}/{f.name}")
        return entries

    keep += scan("bgm", "bgm")
    keep += scan("sfx", "sfx")
    if not keep:
        return None
    return f"<ver>{NES_VER}\n" + "\n".join(keep) + "\n"


def cmd_build(args) -> int:
    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"error: {folder} is not a directory", file=sys.stderr)
        return 2
    scale = args.scale

    # --- key source (where the tile keys come from) ---
    source = Path(args.source).resolve() if args.source else None
    if source is None:
        for cand in (folder / "textures" / "hires.txt", folder / "auto" / "textures" / "hires.txt"):
            if cand.exists():
                source = cand
                break
    if source is None or not source.is_file():
        print("error: no tile-key source; run the emulator bootstrap (auto/textures/hires.txt) or pass --source", file=sys.stderr)
        return 2

    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    header, tiles, audio_refs, body = _parse_source(lines)
    if not tiles:
        print(f"error: key source has no <tile> entries: {source}", file=sys.stderr)
        return 2

    # scale: --scale wins, else the source header's <scale>, else 2. The
    # output header always declares it (a missing <scale> would make the host
    # and lint read the manifest at scale 1 while the sheets are 8*scale).
    src_scale = None
    for h in header:
        if h.startswith("<scale>"):
            src_scale = int(h[7:].strip())
            break
    if scale is None:
        scale = src_scale if src_scale is not None else 2
    if scale < 1 or scale > 10:
        print(f"error: scale {scale} out of range (1..10)", file=sys.stderr)
        return 2

    # --- sheets: 16-column grids; cells map to keys through sheet order ---
    sheets_dir = folder / "textures" / "sheets"
    if not sheets_dir.is_dir():
        print(f"error: no textures/sheets/ folder with the author sheets: {sheets_dir}", file=sys.stderr)
        return 2

    # ADR-0153 sheets are recognised by their sidecar; everything else that is
    # a PNG and not an `*.orig.png` reference twin stays on the ADR-0049
    # 16-column path.
    sheet_docs, owned = _load_sheet_docs(sheets_dir)
    sheets = sorted(p for p in sheets_dir.iterdir()
                    if p.suffix.lower() == ".png" and p not in owned and not _is_reference_png(p))
    for p in sorted(owned):
        if p.is_file() and not any(sd.png_path == p for sd in sheet_docs):
            print(f"info: {p.name} has a sidecar this build could not use — left untouched, no <tile> emitted for it")
    if not sheets and not sheet_docs:
        print(f"error: no PNG sheets in {sheets_dir}", file=sys.stderr)
        return 2

    # An ADR-0153 sheet may be painted at any integer upscale of what the
    # builder emitted; that factor IS the pack scale, since a hires.txt has a
    # single <scale> for every <img> (MEP-v1 §2.1). An explicit --scale, or a
    # legacy sheet that already pins the geometry, wins instead — and then a
    # disagreeing sheet is a build error rather than a silent mis-slice.
    try:
        sheet_scale = _sheet_scale(sheet_docs)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if sheet_scale is not None:
        if args.scale is None and not sheets:
            if sheet_scale != scale:
                print(f"info: scale {sheet_scale} taken from the textures/sheets/ art (key source said {scale})")
            scale = sheet_scale
        elif sheet_scale != scale:
            why = "--scale" if args.scale is not None else "the legacy 16-column sheets"
            print(f"error: textures/sheets/ art is painted at {sheet_scale}x but {why} pins scale {scale}; "
                  f"re-scale the sheets by a whole factor or pass --scale {sheet_scale}", file=sys.stderr)
            return 2

    try:
        cell_sizes = [_sheet_layout(p, scale) for p in sheets]
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    total_cells = sum(cell_sizes)
    if total_cells < len(tiles):
        # With ADR-0153 sheets present the key source is a key/attribute
        # source, not a cell budget: those sheets carry their own keys.
        if not sheet_docs:
            print(f"error: sheets hold {total_cells} cell(s) but the key source has {len(tiles)} tile key(s)", file=sys.stderr)
            return 2
        print(f"info: legacy sheets hold {total_cells} cell(s) of the {len(tiles)} key(s); the rest come from the ADR-0153 sheets")
    if total_cells > len(tiles):
        print(f"info: sheets hold {total_cells} cell(s), only {len(tiles)} are referenced; trailing cells stay unused")

    offsets = []
    acc = 0
    for n in cell_sizes:
        offsets.append(acc)
        acc += n

    # --- regenerate textures/hires.txt ---
    # Header carried over with <scale> pinned to the scale actually used;
    # <ver> and <scale> are always present so the manifest can never be read
    # at a wrong scale/legacy version.
    has_ver = any(h.startswith("<ver>") for h in header)
    has_scale = any(h.startswith("<scale>") for h in header)
    out_header = []
    for h in header:
        if h.startswith("<scale>"):
            out_header.append(f"<scale>{scale}")
        else:
            out_header.append(h)
    if not has_ver:
        out_header.insert(0, f"<ver>{NES_VER}")
    if not has_scale:
        out_header.append(f"<scale>{scale}")
    cell = 8 * scale

    # One slot per emitted <img>, in emission order: the ADR-0049 16-column
    # sheets first (unchanged), then the ADR-0153 sheets. Each slot collects
    # (key, condition, fields) entries; the img index is filled in after the
    # precedence pass, so an ADR-0153 sheet whose every tile lost never
    # occupies an index.
    slots = []
    for i, p in enumerate(sheets):
        entries = []
        for k in range(offsets[i], offsets[i] + cell_sizes[i]):
            if k >= len(tiles):
                break
            cond, raw = tiles[k]
            fields = raw.split(",")
            if len(fields) < 6:
                print(f"error: key source <tile> #{k} has only {len(fields)} fields: {raw}", file=sys.stderr)
                return 2
            cell_in_sheet = k - offsets[i]
            fields[3] = str((cell_in_sheet % 16) * cell)
            fields[4] = str((cell_in_sheet // 16) * cell)
            # A legacy 16-column sheet has no reference twin to diff against,
            # so its cells always count as painted and it relies on rank 0.
            entries.append(((cond, fields[1].strip().upper(), fields[2].strip().upper()), cond, fields, True))
        slots.append({
            "rel": f"sheets/{p.name}", "rank": 0, "always": True,
            "comment": _emit_comment(f"sheets/{p.name}", cell_sizes[i]), "entries": entries,
        })

    # ADR-0153: the sidecar carries each crop's exact hires.txt key, so the
    # remaining <tile> fields (condition prefix, brightness, defaultTile, ...)
    # are carried over from the key source when it knows the key, and default
    # to "1,N" for a key the bootstrap never recorded.
    keysrc_attrs = {}
    for cond, raw in tiles:
        f = [x.strip() for x in raw.split(",")]
        if len(f) >= 6:
            keysrc_attrs.setdefault((f[1].upper(), f[2].upper()), (cond, f[5:]))
    for sd in sheet_docs:
        try:
            crops = _slice_sheet(sd, scale, sheets_dir)
        except BuildError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        entries = []
        seen = {}
        repeats = 0
        for x, y, data, pal, edited in crops:
            cond, rest = keysrc_attrs.get((data, pal), ("", ["1", "N"]))
            key = (cond, data, pal)
            row = (key, cond, ["0", data, pal, str(x), str(y)] + list(rest), edited)
            at = seen.get(key)
            if at is not None:
                # The same metatile placed twice on one sheet: only one crop can
                # own the key, and a painted instance beats an untouched one.
                repeats += 1
                if edited and not entries[at][3]:
                    entries[at] = row
                continue
            seen[key] = len(entries)
            entries.append(row)
        if repeats:
            print(f"info: {sd.name}: {repeats} crop(s) repeat a tile key already taken by an earlier crop of the same sheet")
        rel = f"sheets/{sd.name}"
        slots.append({
            "rel": rel, "rank": sd.rank, "always": False,
            "comment": _emit_sheet_comment(rel, sd.kind, len(entries), sd.json_path.name),
            "entries": entries,
        })

    # Precedence (ADR-0153 §4): a cell only claims a tile key when it was
    # actually painted, measured against the `*.orig.png` twin. A painted cell
    # always beats an untouched one, whatever their kinds; between two painted
    # cells - and between two untouched ones - the static rank decides, ties
    # broken by emission order (later wins). Every override is logged, so
    # nothing silently disappears.
    winner = {}
    for order, slot in enumerate(slots):
        for pos, entry in enumerate(slot["entries"]):
            key = entry[0]
            edited = entry[3] if len(entry) > 3 else True
            score = (1 if edited else 0, slot["rank"], order)
            prev = winner.get(key)
            if prev is not None:
                why = "painted" if edited and not prev[2][0] else "precedence"
                if score < prev[2]:
                    lost = "untouched" if prev[2][0] and not edited else "precedence"
                    print(f"info: {slot['rel']} loses tile {key[1]}/{key[2]} to {slots[prev[0]]['rel']} ({lost})")
                    continue
                print(f"info: {slot['rel']} overrides tile {key[1]}/{key[2]} from {slots[prev[0]]['rel']} ({why})")
            winner[key] = (order, pos, score)
    kept = {(o, p) for o, p, _s in winner.values()}

    out_lines = list(out_header)
    img_index = 0
    emitted = 0
    for order, slot in enumerate(slots):
        live = [(pos, e) for pos, e in enumerate(slot["entries"]) if (order, pos) in kept]
        if not live and not slot["always"]:
            print(f"info: {slot['rel']} contributes no tile of its own — no <img> emitted")
            continue
        out_lines.extend(slot["comment"])
        out_lines.append(f"<img>{slot['rel']}")
        for _pos, (_key, cond, fields, *_rest) in live:
            fields = list(fields)
            fields[0] = str(img_index)
            out_lines.append(f"{cond}<tile>{','.join(fields)}")
        emitted += len(live)
        img_index += 1
    out_lines.extend(body)

    textures_dir = folder / "textures"
    textures_dir.mkdir(parents=True, exist_ok=True)

    # A background PNG referenced by the body that is not under textures/
    # yet is copied up from auto/textures (the author keeps their assets).
    # The tag may carry a condition prefix ([cond]<background>...) — the only
    # form the emulator writes for captured-screen backgrounds.
    _BG_TAG = re.compile(r"^(\[[^\]]*\])?<background>")
    for b in body:
        m = _BG_TAG.match(b)
        if not m:
            continue
        name = b[m.end():].split(",")[0].strip()
        if not name:
            continue
        target = textures_dir / name
        if target.exists():
            continue
        auto_cand = folder / "auto" / "textures" / name
        if auto_cand.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(auto_cand.read_bytes())
            print(f"info: copied background {name} from auto/textures into textures/")

    hires = textures_dir / "hires.txt"
    hires.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"built {hires} — {emitted} tile(s), {img_index} sheet(s), scale {scale}"
          + (f" ({len(sheet_docs)} ADR-0153 sheet(s))" if sheet_docs else ""))

    # --- regenerate audio/hires.txt (new OGGs into audio/) ---
    system = None
    for h in header:
        if h.startswith("<system>"):
            system = h[8:].strip().lower()
            break
    existing_audio = folder / "audio" / "hires.txt"
    seed = audio_refs
    if existing_audio.exists():
        seed = [l for l in existing_audio.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    if system is not None and system != "nes":
        print(f"info: audio manifest skipped — OGG replacement is NES-only (got <system>{system})")
    audio_manifest = _build_audio_manifest(folder, system, seed)
    if audio_manifest:
        (folder / "audio").mkdir(parents=True, exist_ok=True)
        (folder / "audio" / "hires.txt").write_text(audio_manifest, encoding="utf-8")
        print(f"built {folder / 'audio' / 'hires.txt'}")
    elif existing_audio.exists():
        existing_audio.unlink()
        print(f"info: removed {existing_audio} (no OGGs to reference)")

    # --- the linter is the gate ---
    return _run_lint(folder, quiet=args.quiet)


def _derive_sections(folder: Path) -> dict:
    """MEP-v1 §3.1 sections from the built tree (mirror of
    mep_recipe._derive_sections for the ADR-0049 layout)."""
    sections = {}
    if (folder / "textures" / "hires.txt").exists():
        sections["textures"] = {"path": "textures/"}
    # audio/hires.txt only: mep_lint's pack.json probe validates a section
    # against `audio/hires.txt`, not the fingerprints.json alt-probe the
    # convention scanner uses, so a fingerprint-only folder keeps no audio
    # section in pack.json (the OGGs are simply not rendered yet).
    if (folder / "audio" / "hires.txt").exists():
        sections["audio"] = {"path": "audio/"}
    if (folder / "synth" / "preset.cfg").exists():
        sections["synth"] = {"path": "synth/preset.cfg"}
    return sections


def _no_intro_sha1(rom: Path) -> str:
    """MEP-v1 §4: the NES hash covers the payload minus the 16-byte header
    and trainer, limited to the PRG+CHR size the header declares (bytes 4/5,
    NES 2.0 MSBs in byte 9) so a dump with trailing junk matches its clean
    No-Intro entry — mirroring the host's ComputeNoIntroSha1 (ADR-0044)."""
    data = rom.read_bytes()
    ext = rom.suffix.lower()
    end = len(data)
    offset = 0
    if ext == ".nes" and data[:4] == b"NES\x1a":
        offset = 16 + (512 if data[6] & 0x04 else 0)
        prg_units = data[4]
        chr_units = data[5]
        if (data[7] & 0x0C) == 0x08 and (data[9] & 0x0F) != 0x0F and (data[9] >> 4) != 0x0F:
            prg_units |= (data[9] & 0x0F) << 8
            chr_units |= (data[9] >> 4) << 8
        declared = offset + prg_units * 0x4000 + chr_units * 0x2000
        if declared > offset and declared < end:
            end = declared
    elif ext in {".sfc", ".smc", ".swc", ".fig", ".bs", ".st"} and len(data) % 1024 == 512:
        offset = 512
    return hashlib.sha1(data[offset:end]).hexdigest().upper()


def _system_for(rom: Path) -> str:
    return {
        ".nes": "nes", ".gb": "gb", ".gbc": "gbc", ".sms": "sms", ".gg": "gg",
        ".sg": "sg1000", ".sfc": "snes", ".smc": "snes",
    }.get(rom.suffix.lower(), "nes")


def cmd_pack(args) -> int:
    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"error: {folder} is not a directory", file=sys.stderr)
        return 2

    existing = {}
    pack_json = folder / "pack.json"
    if pack_json.exists():
        existing = json.loads(pack_json.read_text(encoding="utf-8"))

    if args.rom:
        rom = Path(args.rom).resolve()
        if not rom.is_file():
            print(f"error: ROM not found: {rom}", file=sys.stderr)
            return 2
        targets = [{"system": _system_for(rom), "sha1": _no_intro_sha1(rom)}]
    elif args.system and args.sha1:
        targets = [{"system": args.system, "sha1": args.sha1.upper()}]
    elif existing.get("targets"):
        targets = existing["targets"]
    else:
        print("error: need --rom, or --system + --sha1, or an existing pack.json with targets", file=sys.stderr)
        return 2

    body = {
        "mep": existing.get("mep") or "1.1.0",
        "name": args.name or existing.get("name") or folder.name,
        "version": args.version or existing.get("version") or "1.0.0",
        "license": args.license or existing.get("license") or "NOASSERTION",
        "targets": targets,
    }
    if args.author or existing.get("author"):
        body["author"] = args.author or existing["author"]
    # Carry over optional MEP-v1 §3.1 fields a re-run must not silently drop
    # (patches[] gates ROM patches at the MEP layer; ADR-0044).
    for optional in ("patches", "crc32", "md5"):
        if existing.get(optional):
            body[optional] = existing[optional]
    sections = _derive_sections(folder)
    if not sections:
        print("error: nothing to pack — no textures/, audio/ or synth/ layer with a manifest", file=sys.stderr)
        return 2
    body["sections"] = sections
    pack_json.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    out = Path(args.out).resolve() if args.out else folder.with_name(f"{body['name']}-{body['version']}.zip")
    files = {}
    for f in sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "pack.json"):
        if out == f:
            continue  # --out inside the folder must not embed a prior zip
        files[f.relative_to(folder).as_posix()] = f.read_bytes()
    # pack.json first at the root; everything else lexical (deterministic zip).
    ordered = {"pack.json": (json.dumps(body, indent=2) + "\n").encode("utf-8")}
    ordered.update(files)

    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(out, "w") as zf:
            for name, data in ordered.items():
                info = zipfile.ZipInfo(filename=name, date_time=FIXED_DATE_TIME)
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o644 << 16
                zf.writestr(info, data)
    except (UnicodeEncodeError, UnicodeDecodeError) as e:
        print(f"error: cannot zip the folder — non-UTF-8 file name: {e}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"packed {out} ({len(ordered)} entries, sha256 {digest})")

    rc = _run_lint(out, quiet=args.quiet)
    if rc != 0:
        return rc
    print(f"OK: {out} lints clean")
    return 0


def cmd_rename_audio_id(args) -> int:
    folder = Path(args.folder).resolve()
    old_id, new_id = args.old_id, args.new_id
    if not folder.is_dir():
        print(f"error: {folder} is not a directory", file=sys.stderr)
        return 2
    if not old_id or not new_id or old_id == new_id:
        print("error: need two distinct non-empty audio ids", file=sys.stderr)
        return 2

    changed = []

    # fingerprints.json: the track's `id` and its `midi` path.
    fp = folder / "audio" / "fingerprints.json"
    if fp.exists():
        data = json.loads(fp.read_text(encoding="utf-8"))
        for t in data.get("tracks", []):
            if t.get("id") != old_id:
                continue
            t["id"] = new_id
            midi = t.get("midi", "")
            t["midi"] = re.sub(r"(^|/)" + re.escape(old_id) + r"\.mid$", r"\g<1>" + new_id + ".mid", midi)
            changed.append("fingerprints.json")
        fp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # Physical files: midi/<id>.mid, bgm/<id>.ogg, sfx/<id>.ogg.
    for sub, ext in (("midi", ".mid"), ("bgm", ".ogg"), ("sfx", ".ogg")):
        src = folder / "audio" / sub / f"{old_id}{ext}"
        if not src.exists():
            continue
        dst = folder / "audio" / sub / f"{new_id}{ext}"
        if dst.exists():
            print(f"error: {dst} already exists", file=sys.stderr)
            return 1
        src.rename(dst)
        changed.append(f"audio/{sub}/{new_id}{ext}")

    # audio/hires.txt file references (bgm/<id>.ogg / sfx/<id>.ogg).
    ah = folder / "audio" / "hires.txt"
    if ah.exists():
        text = ah.read_text(encoding="utf-8")
        n = re.sub(r"(^|[,/])" + re.escape(old_id) + r"\.ogg", r"\g<1>" + new_id + ".ogg", text)
        if n != text:
            ah.write_text(n, encoding="utf-8")
            changed.append("audio/hires.txt")

    if not changed:
        print(f"info: audio id '{old_id}' not found in {folder}")
        return 0
    print(f"renamed '{old_id}' -> '{new_id}': {', '.join(changed)}")
    return 0


def _run_lint(target, quiet: bool) -> int:
    argv = ["mep_build.py", str(target)]
    if quiet:
        argv.append("--quiet")
    rc = mep_lint.main(argv)
    if rc != 0:
        print(f"error: lint failed ({target})", file=sys.stderr)
    return rc


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `mep_build.py <folder>` == `build <folder>` (PRD primary form).
    if argv and argv[0] not in ("build", "pack", "rename-audio-id", "-h", "--help"):
        argv.insert(0, "build")

    p = argparse.ArgumentParser(
        prog="mep_build.py",
        description="Author-side MEP pack builder: build textures/audio manifests from sheets + OGGs, then pack a deterministic zip.",
    )
    sub = p.add_subparsers(dest="cmd")
    b = sub.add_parser("build", help="regenerate textures/hires.txt + audio/hires.txt from textures/sheets/ and audio/")
    b.add_argument("folder")
    b.add_argument("--scale", type=int, help="cell size = 8*scale (default: the key source's <scale>, else 2)")
    b.add_argument("--source", help="hires.txt carrying the tile keys (default: textures/hires.txt, then auto/textures/hires.txt)")
    b.add_argument("--quiet", action="store_true", help="suppress lint info findings")
    b.set_defaults(func=cmd_build)
    pk = sub.add_parser("pack", help="write pack.json and zip the folder deterministically")
    pk.add_argument("folder")
    pk.add_argument("--out", help="output zip path (default: <name>-<version>.zip next to the folder)")
    pk.add_argument("--rom", help="target ROM; No-Intro sha1 is computed for it")
    pk.add_argument("--system")
    pk.add_argument("--sha1")
    pk.add_argument("--name")
    pk.add_argument("--version")
    pk.add_argument("--author")
    pk.add_argument("--license")
    pk.add_argument("--quiet", action="store_true")
    pk.set_defaults(func=cmd_pack)
    ra = sub.add_parser("rename-audio-id", help="rename an enumerated trackNN/sfxNN id across fingerprints.json + midi/bgm/sfx files")
    ra.add_argument("folder")
    ra.add_argument("old_id")
    ra.add_argument("new_id")
    ra.set_defaults(func=cmd_rename_audio_id)

    args = p.parse_args(argv)
    if not hasattr(args, "func"):
        p.print_usage()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
