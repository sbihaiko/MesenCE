"""Host-free engine for the composition editor (ADR-0165, F9.18).

Opens a pack recorded since F9.17 (one whose `textures/sheets/` carries
`adjacency.json`), resolves node ids to art, and answers the two queries
ADR-0164 §5 needs: the seed -> rank -> lock -> recompute loop inside a layer
and the sprite Y-band membership a scene is materialised from. A figure's
layout comes from `sheets/poses.json` when the pack carries one (ADR-0170 §4)
and from the ADR-0168 §2 `evidence[]` walk when it does not. Exports a
composition as an ordinary `object`/`sprite` sidecar (`usrNNN`) with
`composed`/`seed`/`locked` and, for a sprite band, `band` — legal `mep_build`
input, rank inherited from `_SHEET_RANK` by `kind`.

The tree's codecs are reused, not duplicated: PNG decoding through
`mep_build._png_pixels` (the tree's single decoder) and the RGBA `Image`
plus `read_png`/`write_png` from `sheet_repaint`. This module never imports
tkinter, so `test_compose_engine.py` and CI run headless.
"""

import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mep_build  # noqa: E402 — PNG decoder (_png_pixels) and the sheet loader
import sheet_repaint  # noqa: E402 — Image/read_png/write_png, stdlib RGBA codec

GUTTER = 1  # kSheetGutter (TileSheetTypes.h): the cell grid's transparent margin
BAND_QUANTUM = 8  # ADR-0164 §1: sprite floors are quantised to 8 px (Y + 8)
SHEET_VERSION = 1  # mep_build's ADR-0153 v1 schema
#Below this alpha a source pixel does not cover what it is pasted over: a
#sprite tile is mostly transparent, so pasting one opaquely would erase the
#neighbour it overlaps in a composed pose. Same value the scene spike
#(`spike_compose_scene.paste_alpha`) has always used.
_ALPHA_CUTOFF = 128
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
    __slots__ = ("cell", "appearances", "floors", "tiles", "screen_fixed")

    def __init__(self, d):
        self.cell = int(d["cell"])
        self.appearances = int(d.get("appearances") or 0)
        self.floors = [(int(f.get("bottom") or 0), int(f.get("count") or 0)) for f in (d.get("floors") or [])]
        self.tiles = d.get("tiles") or []
        # ADR-0173: the recorder saw this shape pinned to the screen for the
        # whole capture (a HUD bar, a menu icon), so its floors[] are where it
        # is painted, not a ground it stands on. Absent in a pack recorded
        # before the ADR, and absence reads as "not classified" — the bands of
        # such a pack are exactly what they were.
        self.screen_fixed = bool(d.get("screenFixed"))

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
        the Y bands a scene can materialise. Screen-fixed shapes are not
        standing on anything (ADR-0173), so a band only they reach is not a
        band at all."""
        bands = set()
        for node in self.sp.values():
            if node.screen_fixed:
                continue
            bands.update(bottom for bottom, _ in node.floors)
        return sorted(bands)

    def band_members(self, band: int) -> list:
        """Sprite nodes whose `floors[]` includes `band`, most-seen first.

        A screen-fixed shape is never a member: it reaches the band by being
        painted across it, and offering the artist a slice of the HUD as
        something that shares this ground is the defect ADR-0173 names. The
        file keeps its floors[] either way — this is the consumer's filter,
        not a hole in the evidence."""
        return sorted(
            (c for c, n in self.sp.items() if n.on_floor(band) and not n.screen_fixed),
            key=lambda c: (-self.sp[c].appearances, c),
        )


# ---- poses.json (ADR-0170) and the walk it supersedes ----------------------

POSES_FILE = "poses.json"
POSES_VERSION = 1

# ADR-0168 §2 step 3's cross-pose guard, as `spike_compose_scene` shipped it:
# the share of the strongest group edge below which an edge is treated as a
# cross-pose accident rather than a neighbour relation. A judgement call, not a
# measured threshold (ADR-0168 §3) — kept verbatim so a pack without a pose
# sidecar composes exactly as it does today.
WALK_EDGE_COUNT_FLOOR = 0.25


def walk_layout(nodes, evidence):
    """The ADR-0168 §2 `evidence[]` walk: positions, in 8 px tile units, of a
    `sprNNN` group's nodes, recovered by walking the sheet's ordered tile-pair
    offsets out from the first cell.

    This is a **heuristic** and ADR-0168 §3 labels it as one: a group spans
    several animation frames, the pack records no per-frame membership, so the
    walk guesses a pose by taking edges most-observed first and refusing a slot
    that is already taken. ADR-0170 §4 supersedes it wherever `poses.json`
    exists — but only there. A pack recorded before that sidecar is a
    legitimate input forever, so this is the live fallback, not dead code.

    A node whose remaining edges all point at taken slots stays unplaced and is
    simply absent from the returned map (ADR-0168 §2: never drawn at a guessed
    position)."""
    nodes = [n for n in nodes if isinstance(n, int)]
    if not nodes:
        return {}
    edges = sorted((e for e in (evidence or []) if isinstance(e, dict)),
                   key=lambda e: -(e.get("count") or 0))
    if edges:
        floor = (edges[0].get("count") or 0) * WALK_EDGE_COUNT_FLOOR
        edges = [e for e in edges if (e.get("count") or 0) >= floor]
    pos = {nodes[0]: (0, 0)}
    taken = {(0, 0)}
    progress = True
    while progress:
        progress = False
        for e in edges:
            try:
                a, b, dx, dy = e["a"], e["b"], e["dx"], e["dy"]
            except KeyError:
                continue
            if a in pos and b not in pos:
                cand, who = (pos[a][0] + dx, pos[a][1] + dy), b
            elif b in pos and a not in pos:
                cand, who = (pos[b][0] - dx, pos[b][1] - dy), a
            else:
                continue
            if cand in taken:
                continue
            pos[who] = cand
            taken.add(cand)
            progress = True
    return pos


class Pose:
    """One entry of `poses.json`: a silhouette the recorder actually saw in a
    single OAM frame, normalised to its own top-left (ADR-0170 §1)."""

    __slots__ = ("id", "frames", "size", "tiles", "fusion_of")

    def __init__(self, pose_id, frames, size, tiles, fusion_of=()):
        self.id = pose_id
        self.frames = frames
        self.size = size          # (cols, rows) in cells, as the file states it
        self.tiles = tiles        # {node: (dx, dy)}, 8 px cell offsets
        # ADR-0177: the pose ids this entry's tiles split into, when the
        # recorder classified it as two figures that touched. Empty means "not
        # classified" — a pack recorded before ADR-0177 has it empty
        # everywhere, which is exactly how it read before the field existed.
        self.fusion_of = tuple(fusion_of)

    @property
    def fused(self) -> bool:
        """True when the recorder labelled this entry a fusion (ADR-0177).

        False covers both "classified and not a fusion" and "never
        classified" — the file cannot tell them apart, and a consumer that
        needs to must look at whether *any* entry carries the field."""
        return bool(self.fusion_of)

    def layout(self) -> dict:
        """The figure's layout — the same shape `walk_layout` returns."""
        return dict(self.tiles)

    def extent(self):
        """(cols, rows) the placed tiles actually span. `size` is what the file
        claims; this is what its `tiles[]` support, which is what a consumer
        that draws them needs after unknown nodes were dropped."""
        if not self.tiles:
            return (0, 0)
        xs = [p[0] for p in self.tiles.values()]
        ys = [p[1] for p in self.tiles.values()]
        return (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


class Poses:
    """`textures/sheets/poses.json` (ADR-0170 §1), the recorder's record of
    which OAM tiles were on screen together in one frame and where.

    Absent, unreadable, of an unknown version or empty of usable entries, the
    file is simply *not there* as far as a consumer is concerned: `load`
    returns None and the caller runs the ADR-0168 walk instead (ADR-0170 §4).
    A malformed sidecar must never cost an artist a composition they can get
    today, so nothing in here raises."""

    __slots__ = ("version", "unit", "frames", "entries", "dropped_tiles", "dropped_poses")

    def __init__(self):
        self.version = POSES_VERSION
        self.unit = 8
        self.frames = 0
        self.entries = []        # [Pose], most-seen first
        self.dropped_tiles = 0   # tiles naming a node outside the vocabulary
        self.dropped_poses = 0   # entries left with nothing to draw

    @staticmethod
    def load(path, vocabulary=None):
        """Read the sidecar, or return None when there is nothing usable in it.

        `vocabulary` is the sprite node index space (`adjacency.json`
        `sprites.nodes[]`, the same space `node` indexes). A tile naming a node
        outside it is dropped rather than trusted — the two files are different
        projections of one stream and ADR-0170's Consequences say nothing
        cross-checks them."""
        path = Path(path)
        if not path.is_file():
            return None
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(doc, dict):
            return None
        version = doc.get("version", POSES_VERSION)
        if not isinstance(version, int) or version != POSES_VERSION:
            return None  # an unknown format: fall back, never guess at it
        raw = doc.get("poses")
        if not isinstance(raw, list) or not raw:
            return None
        p = Poses()
        p.version = version
        try:
            p.unit = int(doc.get("unit") or 8)
        except (TypeError, ValueError):
            p.unit = 8
        try:
            p.frames = int(doc.get("frames") or 0)
        except (TypeError, ValueError):
            p.frames = 0
        for i, entry in enumerate(raw):
            pose = Poses._parse_pose(entry, i, vocabulary, p)
            if pose is None:
                p.dropped_poses += 1
                continue
            p.entries.append(pose)
        if not p.entries:
            return None
        # ADR-0170 §1 states the order (frames desc, then id); re-establish it
        # here so a hand-edited or partially dropped file is still deterministic.
        p.entries.sort(key=lambda e: (-e.frames, e.id))
        return p

    @staticmethod
    def _parse_pose(entry, index, vocabulary, owner):
        if not isinstance(entry, dict):
            return None
        pose_id = entry.get("id")
        if not isinstance(pose_id, str) or not pose_id:
            pose_id = f"pose{index:03d}"
        try:
            frames = int(entry.get("frames") or 0)
        except (TypeError, ValueError):
            frames = 0
        size = entry.get("size")
        if (isinstance(size, (list, tuple)) and len(size) == 2
                and all(isinstance(v, int) for v in size)):
            size = (size[0], size[1])
        else:
            size = None
        tiles = {}
        for t in (entry.get("tiles") or []):
            if not isinstance(t, dict):
                continue
            try:
                node, dx, dy = int(t["node"]), int(t["dx"]), int(t["dy"])
            except (KeyError, TypeError, ValueError):
                continue
            if vocabulary is not None and node not in vocabulary:
                owner.dropped_tiles += 1
                continue
            tiles.setdefault(node, (dx, dy))
        if not tiles:
            return None
        fusion = entry.get("fusionOf")
        if isinstance(fusion, (list, tuple)):
            fusion = tuple(f for f in fusion if isinstance(f, str) and f)
        else:
            fusion = ()
        pose = Pose(pose_id, frames, size, tiles, fusion)
        if size is None:
            pose.size = pose.extent()
        return pose

    def by_id(self, pose_id):
        for e in self.entries:
            if e.id == pose_id:
                return e
        return None

    def containing(self, node: int) -> list:
        """Poses whose `tiles[]` hold `node`, most-seen first."""
        return [e for e in self.entries if node in e.tiles]


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
        self._scale = None

    @property
    def name(self) -> str:
        return self.png_path.name

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

    @property
    def scale(self) -> int:
        """N such that the painted sheet is N x its 1x twin, 1 when the twin is
        missing or the pair is not an integer multiple. Same factor
        `mep_build._sheet_scale` derives, read off the pixels rather than the
        sidecar so a sheet an artist resized is measured as it is on disk."""
        if self._scale is None:
            self._scale = self._measure_scale()
        return self._scale

    def _measure_scale(self) -> int:
        if not self.orig_path or not self.orig_path.is_file() or not self.png_path.is_file():
            return 1
        try:
            painted = sheet_repaint.read_png(self.png_path)
            twin = sheet_repaint.read_png(self.orig_path)
        except Exception:
            return 1
        if twin.width <= 0 or twin.height <= 0:
            return 1
        if painted.width % twin.width or painted.height % twin.height:
            return 1
        n = painted.width // twin.width
        return n if n >= 1 and n == painted.height // twin.height else 1

    def cell_image_painted(self, cell: dict, scale: int):
        """The cell's art at `scale`, cropped from the painted sheet itself so a
        composed sheet inherits the upscale the bootstrap emitted (and any paint
        already on it) instead of a nearest blow-up of the twin. Returns None
        when this sheet is not at that scale, leaving the caller its fallback."""
        if scale <= 1 or self.scale != scale or not self.png_path.is_file():
            return None
        img = sheet_repaint.read_png(self.png_path)
        x, y, unit = int(cell["x"]) * scale, int(cell["y"]) * scale, self.unit * scale
        if x < 0 or y < 0 or x + unit > img.width or y + unit > img.height:
            return None
        return img.crop(x, y, unit, unit)


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
        # ADR-0170: the pose sidecar, when the recorder that made this pack
        # wrote one. None for every pack recorded before it — that is the
        # normal case, not an error, and `figure_layout` walks instead.
        self.poses = Poses.load(sheets_dir / POSES_FILE,
                                vocabulary=set(self.adjacency.sp))
        self._bg_home = None   # (canonical node -> (Sheet, cell)) cache
        self._sp_home = None
        self._scale = None

    @property
    def scale(self) -> int:
        """The `<scale>` every sheet of this pack shares (ADR-0153): a bootstrap
        pack is emitted upscaled, with a 1x `*.orig.png` twin beside each sheet.
        A composed sheet has to be written at this factor too, or
        `mep_build.py build` rejects the whole pack ("all sheets of a pack share
        one <scale>") and the compose -> export -> paint -> rebuild loop never
        closes. Sheets that disagree leave the pack at 1x — the build reports
        that mismatch with a better message than this module could."""
        if self._scale is None:
            found = {s.scale for s in self.sheets if s.kind in _ALL_SHEET_KINDS and s.cells}
            self._scale = found.pop() if len(found) == 1 else 1
        return self._scale

    def layer_kinds(self) -> list:
        """Kinds actually present, in _SHEET_RANK order — the layer stack
        (ADR-0164 §5): most generic first. Maps are scene surfaces the canvas
        opens, not a cell stack, so they are excluded here."""
        order = {k: i for i, k in enumerate(("metatiles", "misc", "object", "sprites", "sprite", "hud", "font"))}
        kinds = sorted({s.kind for s in self.sheets if s.kind in _ALL_SHEET_KINDS},
                       key=lambda k: order.get(k, 99))
        return kinds

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

    def has_node_art(self, node: int, sprite: bool) -> bool:
        """Whether `node_art` would resolve pixels for this node. The sprite
        vocabulary is bigger than the sheet that draws it, so a caller
        assembling cells has to ask before it commits to a layout."""
        try:
            return self.node_art(node, sprite) is not None
        except ComposeError:
            return False

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

    def node_art_at(self, node: int, sprite: bool, scale: int):
        """`node_art` at the pack's `<scale>`. The painted sheet that shows the
        node is the source when it is at that scale, so the composed sheet
        carries the same pixels the rest of the pack does; anything else falls
        back to a nearest blow-up of the 1x art (never a resample — ADR-0154
        §7 forbids a soft edge on 8-bit tile art)."""
        if scale <= 1:
            return self.node_art(node, sprite)
        home = self.sprite_home(node) if sprite else self.background_home(node)
        if home is not None:
            painted = home[0].cell_image_painted(home[1], scale)
            if painted is not None:
                return painted
        return self.node_art(node, sprite).upscale(scale)

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

    # -- the figure's layout: pose sidecar first, walk as the fallback -------

    def group_nodes(self, stem: str) -> list:
        """The node ids of a `sprNNN`/`objNNN` group sheet, in `cells[]` order.
        The first one is the figure's anchor (ADR-0168 §2 step 1, §4)."""
        path = self.sheets_dir / f"{stem}.json"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ComposeError(f"{path.name}: not readable as JSON ({e})")
        if not isinstance(doc, dict):
            raise ComposeError(f"{path.name}: not a JSON object")
        return [c["metatile"] for c in (doc.get("cells") or [])
                if isinstance(c, dict) and isinstance(c.get("metatile"), int)]

    def pose_for_anchor(self, anchor: int, members=None):
        """The pose a figure anchored at `anchor` is laid out from, or None.

        ADR-0168 §4 identifies a figure by its anchor node, so the candidates
        are the poses that contain it. Among those the pick is: the one
        covering most of the group's other members (when the caller knows
        them), then most frames, then id — `poses[]` is already in that order,
        so the first hit is the most-seen silhouette the anchor appears in.

        ADR-0170 explicitly leaves *grouping poses of the same subject* open,
        and this resolves nothing of that: it picks one silhouette to lay a
        figure out from, it does not claim the other poses containing the
        anchor are the same character."""
        if not self.poses:
            return None
        hits = self.poses.containing(anchor)
        if not hits:
            return None
        # ADR-0177 §5: laying a figure out from a fused entry hands the artist
        # a figure plus a bystander. Prefer the entries that are figures; fall
        # back to the full list only when every candidate is labelled, so a
        # subject the recorder never saw alone is not lost to the label.
        unfused = [p for p in hits if not p.fused]
        hits = unfused or hits
        if not members:
            return hits[0]
        wanted = set(members)
        best, best_cover = None, -1
        for p in hits:  # already (frames desc, id asc), so > keeps that order
            cover = len(wanted & set(p.tiles))
            if cover > best_cover:
                best, best_cover = p, cover
        return best

    def figure_layout(self, stem: str) -> dict:
        """{node: (dx, dy)} in 8 px tile units for a group sheet's figure.

        ADR-0170 §4, the rule this implements: a pack that has `poses.json`
        takes the layout from it and does **not** run the ADR-0168 §2
        `evidence[]` walk — the walk's occupied-slot heuristic exists only to
        guess what the sidecar states. A pack without the sidecar (everything
        recorded before ADR-0170) walks, exactly as it does today.

        With a sidecar the layout is the *pose's* tiles, which can be more
        nodes than the group sheet holds: S10.a measured a `sprNNN` group to
        be a sub-part of a pose, and ADR-0170 §4 is explicit that "a pose is a
        better figure than a fragment"."""
        return self.figure_layout_detail(stem)[0]

    def figure_layout_detail(self, stem: str):
        """`figure_layout` plus where it came from: `(layout, source, pose)`,
        with `source` one of `"poses"` or `"walk"` and `pose` the `Pose` the
        layout came from (None on the walk path). A caller that reports to an
        artist needs to say which of the two paths produced what it shows."""
        path = self.sheets_dir / f"{stem}.json"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ComposeError(f"{path.name}: not readable as JSON ({e})")
        if not isinstance(doc, dict):
            raise ComposeError(f"{path.name}: not a JSON object")
        nodes = [c["metatile"] for c in (doc.get("cells") or [])
                 if isinstance(c, dict) and isinstance(c.get("metatile"), int)]
        if not nodes:
            return ({}, "walk", None)
        pose = self.pose_for_anchor(nodes[0], nodes[1:])
        if pose is not None:
            return (pose.layout(), "poses", pose)
        return (walk_layout(nodes, doc.get("evidence")), "walk", None)

    # -- the pose as the unit of the sprite layer (ADR-0171) -----------------

    def pose_anchor(self, pose) -> int:
        """The node that identifies `pose` in `seed`/`locked`.

        ADR-0171 §5 keeps those fields naming nodes, so a reopened session has
        to find the pose again from one member. The pick is the pose's
        *rarest* node — fewest `appearances` in the sprite vocabulary, ties
        broken in reading order. A character's poses share the torso and the
        head; what tells them apart is the arm or the leg that moved, which is
        exactly the member seen least often. Anchoring on the common tile
        would make every pose of a character resolve to the same silhouette on
        reopen."""
        sp = self.adjacency.sp

        def rank(item):
            node, (dx, dy) = item
            entry = sp.get(node)
            return (entry.appearances if entry else 0, dy, dx, node)

        return min(pose.tiles.items(), key=rank)[0]

    def pose_bottom_nodes(self, pose) -> list:
        """The pose's bottom row — its members at `max(dy)`, which is the part
        of it that stands on a floor (ADR-0171 §3)."""
        if not pose.tiles:
            return []
        bottom = max(dy for _dx, dy in pose.tiles.values())
        return sorted(n for n, (_dx, dy) in pose.tiles.items() if dy == bottom)

    def pose_band_members(self, band: int) -> list:
        """The poses whose bottom row stands on `band` (ADR-0171 §3).

        A pose belongs to a band when the part of it on the floor does, not
        when any member happens to pass through: a projectile crossing at head
        height must not join a ground band merely because its owner's feet are
        on one."""
        if not self.poses:
            return []
        standing = set(self.adjacency.band_members(band))
        if not standing:
            return []
        out = []
        for pose in self.poses.entries:
            # ADR-0177: a fused entry is two figures that touched. Offering it
            # here puts a figure-plus-bystander in the artist's suggestion
            # list, and both its parts are entries of this same file.
            if pose.fused:
                continue
            if standing.intersection(self.pose_bottom_nodes(pose)):
                out.append(pose)
        return out

    def pose_rank(self, band: int, locked: list, budget: int = 40):
        """Rank the band's poses against the locked set — ADR-0171 §4.

        `score = sum(coFrames(member, locked)) / sqrt(len(members))`. The sum
        is the evidence ADR-0164 persists for exactly this question ("who
        shared the floor at the same moment"); the square root damps the size
        term without reversing it, because a bare sum would rank an 11-tile
        pose above a 4-tile one on size alone and a mean would invert the bias
        into a preference for the fragments ADR-0171 exists to stop promoting.
        This is a ranking heuristic over recorded evidence, not a derived
        quantity.

        Returns `[(anchor, score, pose)]`, most-promising first, dropping a
        pose with no co-presence at all against the locked set — the same rule
        `sprite_rank` applies to a node."""
        locked = list(dict.fromkeys(locked))
        if not locked:
            return []
        taken = set(locked)
        #One candidate per anchor, and the pose shown for it is the one
        #`pose_of` resolves — otherwise the artist locks a silhouette and
        #reopening the session draws a different one, since `locked` names the
        #anchor and nothing else (ADR-0171 §5). Several poses of a character
        #legitimately share their rarest member, so this collapses them to the
        #most-seen one rather than offering the artist five rows that all say
        #the same thing and all lock the same node.
        seen_anchor, seen_pose = set(), set()
        #A silhouette already on the row is not a candidate either. Several
        #anchors resolve to one pose (a member's rarest tile is often shared),
        #so filtering only by anchor offers the artist the picture already
        #composed, one cell to its left.
        for node in locked:
            already = self.pose_of(node)
            if already is not None:
                seen_pose.add(already.id)
        scored = []
        for pose in self.pose_band_members(band):
            members = [n for n in pose.tiles]
            if not members:
                continue
            anchor = self.pose_anchor(pose)
            if anchor in taken or anchor in seen_anchor:
                continue  # already composed, or already offered under this anchor
            seen_anchor.add(anchor)
            shown = self.pose_of(anchor) or pose
            if shown.id in seen_pose:
                continue  # two anchors resolving to one silhouette is one candidate
            seen_pose.add(shown.id)
            members = [n for n in shown.tiles] or members
            co = sum(self.adjacency.co_frames(a, n) for a in locked for n in members)
            if co == 0:
                continue  # never on screen with the locked set -> not a candidate
            scored.append((co / math.sqrt(len(members)), shown.frames, shown.id, anchor, shown))
        scored.sort(key=lambda s: (-s[0], -s[1], s[2]))
        ranked = [(anchor, score, pose) for score, _frames, _pid, anchor, pose in scored]
        return ranked if budget is None else ranked[:budget]

    def pose_of(self, anchor: int):
        """The pose a composed anchor stands for, or None when the pack has no
        sidecar (the caller then composes the bare node, ADR-0171 §1 rung 3)."""
        return self.pose_for_anchor(anchor)

    def pose_art(self, pose):
        """A pose drawn as the silhouette it is, 1x, tightly cropped.

        A member whose art no sheet shows is skipped rather than blanked, the
        same rule ADR-0164 §3 sets for a missing pixel — a hole is honest, a
        black square is a lie about the recording."""
        tiles = pose.tiles
        if not tiles:
            return None
        x0 = min(dx for dx, _dy in tiles.values())
        y0 = min(dy for _dx, dy in tiles.values())
        cols, rows = pose.extent()
        img = sheet_repaint.Image(cols * 8, rows * 8)
        for node, (dx, dy) in sorted(tiles.items()):
            try:
                art = self.node_art(node, sprite=True)
            except ComposeError:
                continue
            ox, oy = (dx - x0) * 8, (dy - y0) * 8
            for row in range(art.height):
                for col in range(art.width):
                    px = art.get(col, row)
                    if px[3] < _ALPHA_CUTOFF:
                        continue
                    tx, ty = ox + col, oy + row
                    if 0 <= tx < img.width and 0 <= ty < img.height:
                        img.set(tx, ty, px)
        return img

    def pose_cells(self, anchors: list):
        """`[(node, dx, dy)]` for a composed run of poses — what `export`
        writes as `cells[]` (ADR-0171 §5: composing poses changes which cells
        land where, not the file).

        Each pose keeps its own shape, so the character appears assembled on
        the sheet instead of spread across a row of slivers, and the poses are
        laid left to right with one empty cell between them. A node already
        placed by an earlier pose is not emitted twice: `mep_build.py` fans a
        painted cell back out by its tile key, so two cells carrying one key
        would be two answers to the same question.

        A member no sheet draws is skipped, not exported: `poses.json` indexes
        the whole sprite vocabulary while the sheet only draws the cells it
        routed, so a real pose can name a node that has no pixels. `pose_art`
        already leaves that hole rather than blanking it; `export` would raise
        on it, which would make such a pose uncomposable."""
        out, placed, pen = [], set(), 0
        for anchor in anchors:
            pose = self.pose_of(anchor)
            if pose is None or not pose.tiles:
                if anchor not in placed:
                    out.append((anchor, pen, 0))
                    placed.add(anchor)
                    pen += 1
                continue
            x0 = min(dx for dx, _dy in pose.tiles.values())
            y0 = min(dy for _dx, dy in pose.tiles.values())
            cols, _rows = pose.extent()
            for node, (dx, dy) in sorted(pose.tiles.items(), key=lambda kv: (kv[1][1], kv[1][0])):
                if node in placed or not self.has_node_art(node, sprite=True):
                    continue
                out.append((node, pen + dx - x0, dy - y0))
                placed.add(node)
            pen += cols + 1
        return out

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

    def compose_sheet(self, kind: str, nodes: list, placements: list = None, scale: int = 1):
        """Lay the kept cells out as the composed sheet, without touching disk.

        Returns `(canvas, cells, columns, unit)` - the pixels `export` writes
        and the sidecar cell records that describe them. `export` is this plus
        the file names, so the editor can show a preview that is the sheet and
        not a second drawing of it: one layout, or the preview lies.

        `placements` is `[(node, cx, cy)]` in cell coordinates, from
        `pose_cells` - the sprite layer composes poses (ADR-0171 §5), and a
        pose keeps its own shape on the sheet so the character appears
        assembled instead of spread across a row of slivers. Without it the
        cells wrap in reading order, which is what the object layer wants.

        `scale` draws that same layout at the pack's `<scale>`: the pixels grow,
        the cell records stay in 1x sheet coordinates, because that is the
        geometry the sidecar describes and `mep_build` multiplies back out."""
        if kind not in ("object", "sprite"):
            raise ComposeError(f"composed kind {kind!r} must be 'object' or 'sprite'")
        if not nodes:
            raise ComposeError("nothing to export")
        scale = max(1, int(scale))
        sprite = kind == "sprite"
        arts, unit = [], None
        for node in nodes:
            art = self.node_art_at(node, sprite, scale)
            if unit is None:
                unit = art.width // scale
            if art.width != unit * scale or art.height != unit * scale:
                raise ComposeError(
                    f"node {node} art is {art.width}x{art.height}, "
                    f"not {unit * scale}x{unit * scale}")
            arts.append(art)
        stride = (unit + GUTTER) * scale
        if placements:
            coords = [(cx, cy) for _n, cx, cy in placements]
            columns = max(cx for cx, _cy in coords) + 1
            rows = max(cy for _cx, cy in coords) + 1
        else:
            columns = max(1, min(len(nodes), 16))
            coords = [(i % columns, i // columns) for i in range(len(nodes))]
            rows = (len(nodes) + columns - 1) // columns
        canvas = sheet_repaint.Image(columns * stride + GUTTER * scale,
                                     rows * stride + GUTTER * scale)
        adj = self.adjacency
        cells = []
        for i, node in enumerate(nodes):
            cx, cy = coords[i]
            x = (GUTTER + cx * (unit + GUTTER)) * scale
            y = (GUTTER + cy * (unit + GUTTER)) * scale
            canvas.paste(arts[i], x, y)
            src = adj.sp.get(node) if sprite else adj.bg.get(node)
            cells.append({
                "index": i,
                "x": x // scale, "y": y // scale,
                "count": src.appearances if sprite and src else (src.count if src else 0),
                "context": "" if sprite else (src.context if src else "scene"),
                "metatile": node,
                "label": "",
                "tiles": src.tiles if src else [],
            })
        return canvas, cells, columns, unit

    def export(self, kind: str, nodes: list, seed, locked: list, band=None,
               to_dir: Path = None, placements: list = None):
        """Write a composed sheet (`usrNNN`) to `to_dir` (default the pack's own
        sheets dir). `kind` is `object` or `sprite`; `nodes` are the kept node
        ids in sheet order; `band` is the quantised bottom for a sprite band.
        Returns the sidecar stem. The sheet is written at the pack's `<scale>`
        and its `*.orig.png` twin at 1x, the same pair every bootstrap sheet
        forms: a pack whose sheets are 4x rejects a 1x sheet outright ("all
        sheets of a pack share one <scale>"), so writing the twin's size here
        would break `mep_build.py build` for the whole pack. The artist paints
        `usrNNN.png` in an image editor and `mep_build.py` fans the painted
        cells back out, as for any sheet."""
        if kind not in ("object", "sprite"):
            raise ComposeError(f"composed kind {kind!r} must be 'object' or 'sprite'")
        if not nodes:
            raise ComposeError("nothing to export")
        canvas, cells, columns, unit = self.compose_sheet(kind, nodes, placements)
        to_dir = Path(to_dir) if to_dir is not None else self.sheets_dir
        if not to_dir.is_dir():
            raise ComposeError(f"{to_dir}: not a folder")
        scale = self.scale
        painted = (self.compose_sheet(kind, nodes, placements, scale=scale)[0]
                   if scale > 1 else canvas.clone())
        name = self.next_free_name(to_dir)
        sheet_repaint.write_png(to_dir / f"{name}.png", painted)
        sheet_repaint.write_png(to_dir / f"{name}.orig.png", canvas)
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
