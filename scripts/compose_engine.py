"""Host-free engine for the composition editor (ADR-0165, F9.18).

Opens a pack recorded since F9.17 (one whose `textures/sheets/` carries
`adjacency.json`), resolves node ids to art, and answers the two queries
ADR-0164 §5 needs: the seed -> rank -> lock -> recompute loop inside a layer
and the sprite Y-band membership a scene is materialised from. Exports a
composition as an ordinary `object`/`sprite` sidecar (`usrNNN`) with
`composed`/`seed`/`locked` and, for a sprite band, `band` — legal `mep_build`
input, rank inherited from `_SHEET_RANK` by `kind`.

The tree's codecs are reused, not duplicated: PNG decoding through
`mep_build._png_pixels` (the tree's single decoder) and the RGBA `Image`
plus `read_png`/`write_png` from `sheet_repaint`. This module never imports
tkinter, so `test_compose_engine.py` and CI run headless.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mep_build  # noqa: E402 — PNG decoder (_png_pixels) and the sheet loader
import sheet_repaint  # noqa: E402 — Image/read_png/write_png, stdlib RGBA codec

GUTTER = 1  # kSheetGutter (TileSheetTypes.h): the cell grid's transparent margin
BAND_QUANTUM = 8  # ADR-0164 §1: sprite floors are quantised to 8 px (Y + 8)
SHEET_VERSION = 1  # mep_build's ADR-0153 v1 schema
_COMPOSED_RE = re.compile(r"^usr(\d{3})\.json$")


class ComposeError(Exception):
    """A pack that cannot be composed: no adjacency.json, an unreadable sidecar,
    a node whose art is not on disk. The message tells the artist the fix (re-run
    the bootstrap, compose from the screen layer) — never a silent blank."""


def _nearest_downscale(img, scale):
    """Nearest-neighbour reduction of an N x capture crop back to 1x. The
    screen reference twin was upscaled by N without resampling, so sampling
    every Nth pixel recovers the original art exactly — no soft edge, which
    ADR-0154 §7 forbids on 8-bit tile art."""
    w, h = img.width // scale, img.height // scale
    out = sheet_repaint.Image(w, h)
    for y in range(h):
        for x in range(w):
            src = img.offset(x * scale, y * scale)
            dst = out.offset(x, y)
            out.px[dst:dst + 4] = img.px[src:src + 4]
    return out


# ---- adjacency.json --------------------------------------------------------

class _AdjNode:
    __slots__ = ("cell", "count", "context", "out_e", "out_s", "in_e", "in_s", "tiles", "screens")

    def __init__(self, d):
        self.cell = int(d["cell"])
        self.count = int(d.get("count") or 0)
        self.context = str(d.get("context") or "scene")
        self.out_e = int(d.get("outE") or 0)
        self.out_s = int(d.get("outS") or 0)
        self.in_e = int(d.get("inE") or 0)
        self.in_s = int(d.get("inS") or 0)
        self.tiles = d.get("tiles") or []
        # ADR-0166 (F9.18): the screens that own this node's pixels, each with
        # the 8 px placement of the node's top-left tile on that screen.
        self.screens = []
        for s in (d.get("screens") or []):
            try:
                self.screens.append({
                    "screen": str(s["screen"]),
                    "x": int(s["x"]),
                    "y": int(s["y"]),
                })
            except (KeyError, TypeError, ValueError):
                continue


class _SpriteNode:
    __slots__ = ("cell", "appearances", "floors", "tiles")

    def __init__(self, d):
        self.cell = int(d["cell"])
        self.appearances = int(d.get("appearances") or 0)
        self.floors = [(int(f.get("bottom") or 0), int(f.get("count") or 0)) for f in (d.get("floors") or [])]
        self.tiles = d.get("tiles") or []

    def on_floor(self, band: int) -> bool:
        return any(bottom == band for bottom, _ in self.floors)


class Adjacency:
    """The ADR-0164 §1 sidecar, indexed the way the two §5 queries need.

    Background nodes carry their degree totals, so a reader recomputes
    ADR-0153 §2's conditional probabilities without summing the edge list;
    sprite nodes carry `floors[]` per shape and the pair list carries
    `coFrames` — the far-field statistics the 32 px histogram cannot answer."""

    def __init__(self):
        self.version = 1
        self.bg = {}          # cell -> _AdjNode
        self.bg_edges = []    # {a, b, dir, count}, complete E/S map
        self._edge = {}       # (a, dir) -> {b: count}
        self.sp = {}          # cell -> _SpriteNode
        self.pairs = []       # {a, b, coFrames, ...}
        self._co = {}         # (min, max) -> coFrames
        self.oam_frames = 0
        self.sp_vocab_size = 0
        self.bg_vocab_size = 0
        self.grid_unit = 8
        self.distinct_screens = 0
        self.sprites_present = False

    @staticmethod
    def load(path: Path) -> "Adjacency":
        path = Path(path)
        if not path.is_file():
            raise ComposeError("no adjacency.json — re-run the bootstrap "
                               "(a pack recorded since F9.17 has one)")
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ComposeError(f"{path.name}: not readable as JSON ({e})")
        if not isinstance(doc, dict):
            raise ComposeError(f"{path.name}: not a JSON object")
        a = Adjacency()
        bg = doc.get("background")
        if not isinstance(bg, dict):
            raise ComposeError(f"{path.name}: no background block")
        a.bg_vocab_size = int(bg.get("vocabularySize") or 0)
        a.grid_unit = int(bg.get("gridUnit") or 8)
        a.distinct_screens = int(bg.get("distinctScreens") or 0)
        for n in bg.get("nodes") or []:
            node = _AdjNode(n)
            a.bg[node.cell] = node
        for e in bg.get("edges") or []:
            a.bg_edges.append(e)
            a._edge.setdefault((int(e["a"]), str(e["dir"])), {})[int(e["b"])] = int(e["count"])
        sp = doc.get("sprites")
        a.sprites_present = isinstance(sp, dict) and bool(sp.get("nodes"))
        if a.sprites_present:
            a.sp_vocab_size = int(sp.get("vocabularySize") or 0)
            a.oam_frames = int(sp.get("oamFrames") or 0)
            for n in sp.get("nodes") or []:
                node = _SpriteNode(n)
                a.sp[node.cell] = node
            for p in sp.get("pairs") or []:
                lo, hi = sorted((int(p["a"]), int(p["b"])))
                a._co[(lo, hi)] = int(p.get("coFrames") or 0)
                a.pairs.append(p)
        return a

    def edge_count(self, source: int, target: int, direction: str) -> int:
        return self._edge.get((source, direction), {}).get(target, 0)

    def out_degree(self, source: int, direction: str) -> int:
        node = self.bg.get(source)
        return node.out_e if direction == "E" else node.out_s if direction == "S" else 0

    def co_frames(self, a_cell: int, b_cell: int) -> int:
        if a_cell == b_cell:
            return 0
        return self._co.get(tuple(sorted((a_cell, b_cell))), 0)

    def floors(self) -> list:
        """Every quantised bottom edge some sprite stands on, sorted ascending —
        the Y bands a scene can materialise."""
        bands = set()
        for node in self.sp.values():
            bands.update(bottom for bottom, _ in node.floors)
        return sorted(bands)

    def band_members(self, band: int) -> list:
        """Sprite nodes whose `floors[]` includes `band`, most-seen first."""
        return sorted(
            (c for c, n in self.sp.items() if n.on_floor(band)),
            key=lambda c: (-self.sp[c].appearances, c),
        )


# ---- the pack --------------------------------------------------------------

class Sheet:
    """One ADR-0153 sidecar plus its twins, wrapped for node lookup."""

    def __init__(self, sheets_dir: Path, sd: mep_build.SheetDoc):
        self.sheets_dir = sheets_dir
        self.doc = sd
        self.kind = sd.kind
        self.unit = sd.unit
        self.gutter = sd.gutter
        self.columns = sd.columns
        self.cells = sd.cells
        self.json_path = sd.json_path
        self.png_path = sd.png_path
        ref = str(sd.doc.get("reference") or "").strip()
        self.orig_path = sheets_dir / ref if ref else None

    @property
    def name(self) -> str:
        return self.png_path.name

    def cell_for_node(self, node: int):
        """The sheet's cell that shows `node`: canonical (`metatile`) first, then
        an alias that absorbed it (F9.7)."""
        for c in self.cells:
            if isinstance(c, dict) and c.get("metatile") == node:
                return c
        for c in self.cells:
            if not isinstance(c, dict):
                continue
            for al in c.get("aliases") or []:
                if isinstance(al, dict) and al.get("metatile") == node:
                    return c
        return None

    def cell_image(self, cell: dict):
        """The cell's 1x art, cropped from the `*.orig.png` twin (the reference,
        never the possibly-painted sheet). Raises when the twin is unusable."""
        if not self.orig_path or not self.orig_path.is_file():
            raise ComposeError(f"{self.name}: no usable *.orig.png twin to source cell art from")
        img = sheet_repaint.read_png(self.orig_path)
        x, y = int(cell["x"]), int(cell["y"])
        if x < 0 or y < 0 or x + self.unit > img.width or y + self.unit > img.height:
            raise ComposeError(f"{self.name}: cell art falls outside the twin ({x},{y},{self.unit})")
        return img.crop(x, y, self.unit, self.unit)


# Node -> art pixel sources, exactly the sheets ADR-0164 §3 names: the
# metatile vocabularies for background, the sprites vocabulary for OAM. A
# `objNNN`/`sprNNN` group is a *layout* a node also appears in, not a source
# the composer pastes from — a node only ever on a group sheet is a
# screen-owned cell (ADR-0156) and resolves through the screen, or not at all.
_BG_ART_KINDS = ("metatiles", "hud", "font", "misc")
_SPRITE_ART_KINDS = ("sprites",)
_ALL_SHEET_KINDS = _BG_ART_KINDS + ("object",) + _SPRITE_ART_KINDS + ("sprite",)


class Pack:
    """A pack folder opened for composition: `textures/sheets/` read through
    mep_build's loader (adjacency skipped silently), adjacency.json on top."""

    def __init__(self, folder: Path):
        folder = Path(folder)
        sheets_dir = folder / "textures" / "sheets"
        if not sheets_dir.is_dir():
            sheets_dir = folder  # allow pointing straight at textures/sheets/
            if not sheets_dir.is_dir():
                raise ComposeError(f"{folder}: not a pack folder with textures/sheets/")
        self.folder = folder
        self.sheets_dir = sheets_dir
        # ADR-0166: whole-screen captures live one level up from the sheets.
        self.backgrounds_dir = (sheets_dir.parent / "backgrounds"
                                if sheets_dir.name == "sheets" else folder.parent / "backgrounds")
        self.docs, self.claimed = mep_build._load_sheet_docs(sheets_dir)
        self.sheets = [Sheet(sheets_dir, sd) for sd in self.docs]
        self.adjacency = Adjacency.load(sheets_dir / "adjacency.json")
        self._bg_home = None   # (canonical node -> (Sheet, cell)) cache
        self._sp_home = None

    def layer_kinds(self) -> list:
        """Kinds actually present, in _SHEET_RANK order — the layer stack
        (ADR-0164 §5): most generic first. Maps are scene surfaces the canvas
        opens, not a cell stack, so they are excluded here."""
        order = {k: i for i, k in enumerate(("metatiles", "misc", "object", "sprites", "sprite", "hud", "font"))}
        kinds = sorted({s.kind for s in self.sheets if s.kind in _ALL_SHEET_KINDS},
                       key=lambda k: order.get(k, 99))
        return kinds

    def sheets_of(self, kind: str) -> list:
        return [s for s in self.sheets if s.kind == kind]

    # -- node -> art ---------------------------------------------------------

    def _homes(self, kinds):
        homes = {}
        for sheet in self.sheets:
            if sheet.kind not in kinds:
                continue
            for cell in sheet.cells:
                if not isinstance(cell, dict):
                    continue
                m = cell.get("metatile")
                if isinstance(m, int):
                    homes.setdefault(("canon", m), (sheet, cell))
                for al in cell.get("aliases") or []:
                    if isinstance(al, dict) and isinstance(al.get("metatile"), int):
                        homes.setdefault(("alias", al["metatile"]), (sheet, cell))
        return homes

    def _node_home(self, node: int, kinds):
        homes = self._homes(kinds)
        if ("canon", node) in homes:
            return homes[("canon", node)]
        if ("alias", node) in homes:
            return homes[("alias", node)]
        return None

    def background_home(self, node: int):
        """The art-sheet cell that shows a background node, or None when no
        sheet shows it (it is screen-owned, ADR-0156)."""
        return self._node_home(node, _BG_ART_KINDS)

    def sprite_home(self, node: int):
        return self._node_home(node, _SPRITE_ART_KINDS)

    def node_art(self, node: int, sprite: bool):
        """The 1x pixels of a node — the source the composition pastes.

        Background resolution mirrors ADR-0164 §3 then ADR-0166: a node a sheet
        shows is cropped from that sheet's `*.orig.png`; a node no sheet shows
        is one a captured screen owns (ADR-0156), and since ADR-0166 the
        adjacency sidecar records which `screenNNN` froze it and where, so the
        tool crops it from `backgrounds/<screen>.orig.png` at the pack's scale.
        A node with neither is still an error, never a silent blank."""
        home = self.sprite_home(node) if sprite else self.background_home(node)
        if home is not None:
            return home[0].cell_image(home[1])
        if sprite:
            raise ComposeError(f"no sheet shows sprite node {node} — re-run the bootstrap")
        return self._screen_art(node)

    def _screen_art(self, node: int):
        """Crop a screen-owned background node out of its owning capture."""
        bg = self.adjacency.bg.get(node)
        if not bg or not bg.screens:
            raise ComposeError(
                f"no sheet shows background node {node}; it is a screen-owned cell (ADR-0156) and "
                "adjacency.json records no owning screen for it (a pack recorded before ADR-0166 "
                "lacks the screens[] field) — compose it from the map/background layer, or re-run "
                "the bootstrap")
        site = bg.screens[0]
        path = self.backgrounds_dir / f"{site['screen']}.orig.png"
        if not path.is_file():
            raise ComposeError(f"{site['screen']}.orig.png is missing under backgrounds/")
        img = sheet_repaint.read_png(path)
        scale = img.width // 256
        if scale < 1 or img.width != 256 * scale or img.height != 240 * scale:
            raise ComposeError(f"{path.name} is not a 256x240 NES capture at an integer scale")
        unit = self.adjacency.grid_unit
        x0, y0 = site["x"] * 8 * scale, site["y"] * 8 * scale
        if x0 < 0 or y0 < 0 or x0 + unit * scale > img.width or y0 + unit * scale > img.height:
            raise ComposeError(f"{site['screen']}: node {node} art falls outside the capture")
        crop = img.crop(x0, y0, unit * scale, unit * scale)
        return _nearest_downscale(crop, scale) if scale > 1 else crop

    # -- the two §5 queries --------------------------------------------------

    def background_rank(self, locked: list, budget: int = 40):
        """Seed -> rank -> lock -> recompute over the background adjacency.

        Every physical adjacency between a locked node `a` and a candidate `c`
        is one directed E/S edge in one of the two source orders (right/down
        from either side covers all four orientations), so the score sums the
        conditional evidence `count / out(a, dir)` over both source orders and
        both directions. This is the mass ADR-0164 persists; nothing is pruned.
        Deterministic: score desc, node id asc."""
        locked = list(dict.fromkeys(locked))
        scores = {}
        for c, node in self.adjacency.bg.items():
            if c in locked:
                continue
            s = 0.0
            for direction in ("E", "S"):
                for a in locked:
                    s += self.adjacency.edge_count(a, c, direction) / self.adjacency.out_degree(a, direction) \
                        if self.adjacency.out_degree(a, direction) else 0.0
                    s += self.adjacency.edge_count(c, a, direction) / self.adjacency.out_degree(c, direction) \
                        if self.adjacency.out_degree(c, direction) else 0.0
            scores[c] = s
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        if budget is None:
            return ranked
        return ranked[:budget]

    def sprite_rank(self, band: int, locked: list, budget: int = 40):
        """Recompute inside a Y band: candidates are the band's members (shapes
        whose bottom edge stands on it), scored by the summed `coFrames` with the
        locked set. `coFrames` is the far-field statistic ADR-0164 persists for
        exactly this — "who shares the floor at the same moment" — so a
        projectile never standing near the seed ranks below the ground enemies."""
        locked = list(dict.fromkeys(locked))
        scores = {}
        for c in self.adjacency.band_members(band):
            if c in locked:
                continue
            co = sum(self.adjacency.co_frames(a, c) for a in locked)
            if co == 0:
                continue  # never on screen with the locked set -> not a candidate
            scores[c] = co
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1],
                                                         -self.adjacency.sp[kv[0]].appearances, kv[0]))
        return ranked if budget is None else ranked[:budget]

    # -- export --------------------------------------------------------------

    def next_free_name(self, in_dir: Path = None) -> str:
        """First unused `usrNNN` stem in `in_dir` (default the pack's own sheets
        dir). Exporting always writes into `to_dir` (ADR-0165 §4: `auto/` until
        painted, `mep/` once it is), so the free-name scan must look there too
        — scanning the pack's own dir regardless would let two exports to the
        same `to_dir` collide and silently overwrite one another's PNG."""
        in_dir = Path(in_dir) if in_dir is not None else self.sheets_dir
        taken = set()
        for jp in in_dir.glob("usr*.json"):
            m = _COMPOSED_RE.match(jp.name)
            if m:
                taken.add(int(m.group(1)))
        n = 0
        while n in taken:
            n += 1
        return f"usr{n:03d}"

    def compose_sheet(self, kind: str, nodes: list):
        """Lay the kept cells out as the composed sheet, without touching disk.

        Returns `(canvas, cells, columns, unit)` - the pixels `export` writes
        and the sidecar cell records that describe them. `export` is this plus
        the file names, so the editor can show a preview that is the sheet and
        not a second drawing of it: one layout, or the preview lies."""
        if kind not in ("object", "sprite"):
            raise ComposeError(f"composed kind {kind!r} must be 'object' or 'sprite'")
        if not nodes:
            raise ComposeError("nothing to export")
        sprite = kind == "sprite"
        arts, unit = [], None
        for node in nodes:
            art = self.node_art(node, sprite)
            if unit is None:
                unit = art.width
            if art.width != unit or art.height != unit:
                raise ComposeError(f"node {node} art is {art.width}x{art.height}, not {unit}x{unit}")
            arts.append(art)
        columns = max(1, min(len(nodes), 16))
        stride = unit + GUTTER
        rows = (len(nodes) + columns - 1) // columns
        canvas = sheet_repaint.Image(columns * stride + GUTTER, rows * stride + GUTTER)
        adj = self.adjacency
        cells = []
        for i, node in enumerate(nodes):
            x = GUTTER + (i % columns) * stride
            y = GUTTER + (i // columns) * stride
            canvas.paste(arts[i], x, y)
            src = adj.sp.get(node) if sprite else adj.bg.get(node)
            cells.append({
                "index": i,
                "x": x, "y": y,
                "count": src.appearances if sprite and src else (src.count if src else 0),
                "context": "" if sprite else (src.context if src else "scene"),
                "metatile": node,
                "label": "",
                "tiles": src.tiles if src else [],
            })
        return canvas, cells, columns, unit

    def export(self, kind: str, nodes: list, seed, locked: list, band=None,
               to_dir: Path = None):
        """Write a composed sheet (`usrNNN`) to `to_dir` (default the pack's own
        sheets dir). `kind` is `object` or `sprite`; `nodes` are the kept node
        ids in sheet order; `band` is the quantised bottom for a sprite band.
        Returns the sidecar stem. The PNG and its `*.orig.png` twin start
        identical (1x); the artist paints `usrNNN.png` in an image editor and
        `mep_build.py` fans the painted cells back out, as for any sheet."""
        if kind not in ("object", "sprite"):
            raise ComposeError(f"composed kind {kind!r} must be 'object' or 'sprite'")
        if not nodes:
            raise ComposeError("nothing to export")
        canvas, cells, columns, unit = self.compose_sheet(kind, nodes)
        to_dir = Path(to_dir) if to_dir is not None else self.sheets_dir
        if not to_dir.is_dir():
            raise ComposeError(f"{to_dir}: not a folder")
        name = self.next_free_name(to_dir)
        sheet_repaint.write_png(to_dir / f"{name}.png", canvas)
        sheet_repaint.write_png(to_dir / f"{name}.orig.png", canvas.clone())
        doc = {
            "version": SHEET_VERSION,
            "kind": kind,
            "gridUnit": unit,
            "gutter": GUTTER,
            "columns": columns,
            "sheet": f"{name}.png",
            "reference": f"{name}.orig.png",
            "composed": True,
            "seed": seed,
            "locked": list(locked),
            "cells": cells,
        }
        if band is not None:
            doc["band"] = {"bottom": int(band), "tolerance": BAND_QUANTUM}
        (to_dir / f"{name}.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return name

    # -- helpers for the GUI layer stack -------------------------------------

    def background_cells(self):
        """(node, Sheet, cell) for every background node an art sheet shows,
        most-seen first — the cells the artist can seed and paste."""
        return self._art_cells(_BG_ART_KINDS, self.adjacency.bg, "count")

    def sprite_cells(self):
        """(node, Sheet, cell) for every OAM shape the sprites vocabulary shows,
        most-seen first."""
        return self._art_cells(_SPRITE_ART_KINDS, self.adjacency.sp, "appearances")

    def _art_cells(self, kinds, node_map, freq_key):
        out, seen = [], set()
        for sheet in self.sheets:
            if sheet.kind not in kinds:
                continue
            for cell in sheet.cells:
                if not isinstance(cell, dict):
                    continue
                m = cell.get("metatile")
                if isinstance(m, int) and m in node_map and m not in seen:
                    seen.add(m)
                    out.append((m, sheet, cell))
        return sorted(out, key=lambda t: -getattr(node_map[t[0]], freq_key))

    def group_sheets(self):
        """The `objNNN`/`sprNNN` group sheets — the builder's own layouts, shown
        as layers an artist may open (their art is not a paste source)."""
        return [s for s in self.sheets if s.kind in ("object", "sprite")]
