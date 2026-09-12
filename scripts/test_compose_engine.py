"""Headless suite for the composition engine (ADR-0165 / F9.18).

The two ADR-0164 acceptance tests run here as ordinary assertions, with no
window: a Ninja Gaiden-style background seed -> lock -> recompute must place
the rest of its `objNNN` group's cells before any decoy, and the Y band under
a hero's bottom edge must rank the recording's ground enemies above a
projectile. Everything builds synthetic packs that mirror the real sidecar
schema (metatiles/sprites/object sheets plus `adjacency.json`), so the suite
needs no ROM, no emulator and no recording.

Run:  python3 scripts/test_compose_engine.py
"""

import json
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_engine as E  # noqa: E402
import sheet_repaint  # noqa: E402 — Image/read_png/write_png for fixtures

_FAILURES = []


def check(cond, name, detail=""):
    if cond:
        print(f"ok   {name}")
    else:
        print(f"FAIL {name}: {detail}")
        _FAILURES.append(name)


def _solid(unit, color):
    img = sheet_repaint.Image(unit, unit)
    row = bytes(color) * unit
    for y in range(unit):
        img.px[y * unit * 4:(y + 1) * unit * 4] = row
    return img


def _node_color(node, band=0):
    r = (node * 37 + band) & 0xFF
    g = (node * 91 + band * 7) & 0xFF
    b = (node * 17 + band * 13) & 0xFF
    return (r, g, b, 255)


def _write_sheet(dirpath, stem, kind, cells, unit, columns, extra=None, scale=1):
    """Sidecar + PNG + orig twin for one ADR-0153 sheet. `cells` is a list of
    dicts already carrying x/y/metatile; each cell's region in the image is a
    solid colour keyed off its metatile, so art is resolvable and comparable."""
    dirpath = Path(dirpath)
    stride = unit + E.GUTTER
    rows = max(1, -(-len(cells) // columns))
    width, height = columns * stride + E.GUTTER, rows * stride + E.GUTTER
    canvas = sheet_repaint.Image(width, height)
    for c in cells:
        m = int(c["metatile"])
        art = _solid(unit, _node_color(m))
        canvas.paste(art, int(c["x"]), int(c["y"]))
    painted = canvas.clone() if scale == 1 else canvas.upscale(scale)
    if scale > 1:
        # Mark the upscaled sheet so a composed sheet sourced from it is
        # distinguishable from a blow-up of the 1x twin: that is the difference
        # between inheriting the pack's art and re-deriving it.
        painted.set(0, 0, (1, 2, 3, 255))
    sheet_repaint.write_png(dirpath / f"{stem}.png", painted)
    sheet_repaint.write_png(dirpath / f"{stem}.orig.png", canvas.clone())
    doc = {
        "version": 1,
        "kind": kind,
        "gridUnit": unit,
        "gridPhase": {"x": 0, "y": 0},
        "hasGrid": True,
        "phaseAdvantage": 0.0,
        "gridConsistency": {"chosen": 1.0, "alt8x8": 1.0},
        "cell": {"w": unit, "h": unit},
        "gutter": E.GUTTER,
        "columns": columns,
        "routedCells": 0,
        "sheet": f"{stem}.png",
        "reference": f"{stem}.orig.png",
        "cells": cells,
    }
    if extra:
        doc.update(extra)
    (dirpath / f"{stem}.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _tiles():
    return [{"tile": "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF", "palette": "0F0F0F0F"}]


def _bg_cell(slot, node, count, context="scene", aliases=None):
    stride = 16 + E.GUTTER
    cell = {
        "index": slot,
        "x": E.GUTTER + (slot % 4) * stride,
        "y": E.GUTTER + (slot // 4) * stride,
        "count": count,
        "context": context,
        "metatile": node,
        "aliases": aliases or [],
        "label": "",
        "tiles": _tiles(),
    }
    return cell


def _sprite_cell(slot, node, appearances):
    stride = 8 + E.GUTTER
    return {
        "index": slot,
        "x": E.GUTTER + (slot % 4) * stride,
        "y": E.GUTTER + (slot // 4) * stride,
        "count": appearances,
        "context": "",
        "metatile": node,
        "aliases": [],
        "label": "",
        "tiles": _tiles(),
    }


# The obj000 group of the acceptance test: metatiles 0..3 strongly linked in a
# ring, decoys 4..6 each tied to the seed by a single weak edge.
_BG_EDGES = [
    {"a": 0, "b": 1, "dir": "E", "count": 100},
    {"a": 1, "b": 2, "dir": "E", "count": 100},
    {"a": 2, "b": 3, "dir": "S", "count": 100},
    {"a": 0, "b": 3, "dir": "S", "count": 100},
    {"a": 0, "b": 4, "dir": "E", "count": 2},
    {"a": 0, "b": 6, "dir": "E", "count": 1},
    {"a": 0, "b": 5, "dir": "S", "count": 2},
]
_BG_NODES = {
    0: (103, 102, 0, 0, 3000),   # (outE, outS, inE, inS, count)
    1: (100, 0, 100, 0, 800),
    2: (0, 100, 100, 0, 700),
    3: (0, 0, 0, 200, 600),
    4: (0, 0, 2, 0, 300),
    5: (0, 0, 0, 2, 250),
    6: (0, 0, 1, 0, 200),
}
_OBJ000 = [0, 1, 2, 3]


def make_pack(root: Path, with_obj_sheet: bool = True, scale: int = 1):
    """A synthetic pack recorded since F9.17: metatiles + sprites + (optionally)
    obj000 sheets and an adjacency.json consistent with the above numbers."""
    sheets = root / "textures" / "sheets"
    sheets.mkdir(parents=True)
    # Background sheet: node 0 absorbs 1 as an alias (F9.7), nodes 2..6 canonical.
    cells = [
        _bg_cell(0, 0, 3000, aliases=[{"metatile": 1, "tiles": _tiles()}]),
        _bg_cell(1, 2, 700),
        _bg_cell(2, 3, 600),
        _bg_cell(3, 4, 300),
        _bg_cell(4, 5, 250),
        _bg_cell(5, 6, 200),
    ]
    _write_sheet(sheets, "metatiles", "metatiles", cells, 16, 4, scale=scale)
    # Object sheet: the group whose members the acceptance test must re-rank
    # first after a seed + lock.
    if with_obj_sheet:
        obj_cells = [_bg_cell(i, m, 100, context="scene") for i, m in enumerate(_OBJ000)]
        _write_sheet(sheets, "obj000", "object", obj_cells, 16, 4, scale=scale)
    # Sprite vocabulary: nodes 0..3 have art (Ryu, two ground enemies, a
    # projectile); node 4 is a far-field decoy with no sheet art.
    sprite_cells = [_sprite_cell(idx, m, (3000, 500, 400, 900)[idx]) for idx, m in enumerate((0, 1, 2, 3))]
    _write_sheet(sheets, "sprites", "sprites", sprite_cells, 8, 4, scale=scale)

    # ADR-0166 (F9.18): whole-screen captures the screen-owned nodes live on.
    # Node 7 is resident (no sheet cell) and is drawn on two captures, at scale
    # 1 and scale 2, at 8 px tile position (x=3, y=2) -> 1x pixel origin (24,16).
    backgrounds = root / "textures" / "backgrounds"
    backgrounds.mkdir(parents=True)
    for cap, scale in (("screen001", 1), ("screen002", 2)):
        frame = sheet_repaint.Image(256 * scale, 240 * scale)
        frame.paste(_solid(16, _node_color(7)).upscale(scale), 24 * scale, 16 * scale)
        sheet_repaint.write_png(backgrounds / f"{cap}.png", frame)
        sheet_repaint.write_png(backgrounds / f"{cap}.orig.png", frame.clone())

    bg_nodes = []
    for node, (out_e, out_s, in_e, in_s, count) in _BG_NODES.items():
        bg_nodes.append({
            "cell": node, "count": count, "context": "scene",
            "outE": out_e, "outS": out_s, "inE": in_e, "inS": in_s,
            "tiles": _tiles(),
        })
    # Two more background nodes: 7 is screen-owned (captures above show it),
    # 8 is resident per the marker but a stale/pre-0166 pack would carry no
    # screens[] — both have no sheet cell, so only 7 resolves to pixels.
    for node, count in ((7, 240), (8, 120)):
        bg_nodes.append({"cell": node, "count": count, "context": "scene",
                         "outE": 0, "outS": 0, "inE": 0, "inS": 0, "tiles": _tiles()})
    bg_nodes[7]["screens"] = [
        {"screen": "screen002", "x": 3, "y": 2},  # first: exercises the scale-2 crop
        {"screen": "screen001", "x": 3, "y": 2},
    ]
    sp_nodes = [
        {"cell": 0, "appearances": 3000,
         "floors": [{"bottom": 176, "count": 2900}, {"bottom": 144, "count": 100}],
         "tiles": _tiles()},
        {"cell": 1, "appearances": 500, "floors": [{"bottom": 176, "count": 400}], "tiles": _tiles()},
        {"cell": 2, "appearances": 400, "floors": [{"bottom": 176, "count": 350}], "tiles": _tiles()},
        {"cell": 3, "appearances": 900,
         "floors": [{"bottom": 128, "count": 800}, {"bottom": 176, "count": 30}], "tiles": _tiles()},
        {"cell": 4, "appearances": 100, "floors": [{"bottom": 176, "count": 60}], "tiles": _tiles()},
        # ADR-0173: a HUD bar, pinned across three bands at once - one of them
        # (192) reached by nothing else, so it is not a band at all.
        {"cell": 5, "appearances": 9000, "screenFixed": True,
         "floors": [{"bottom": 176, "count": 3000}, {"bottom": 128, "count": 3000},
                    {"bottom": 192, "count": 3000}],
         "tiles": _tiles()},
    ]
    pairs = [
        {"a": 0, "b": 1, "coFrames": 480, "count": 300, "offsets": [], "other": 0},
        {"a": 0, "b": 2, "coFrames": 420, "count": 300, "offsets": [], "other": 0},
        {"a": 0, "b": 3, "coFrames": 40, "count": 0, "offsets": [], "other": 0},
    ]
    adj = {
        "version": 1,
        "kind": "adjacency",
        "background": {
            "vocabulary": "metatiles.json",
            "vocabularySize": 9,
            "gridUnit": 16,
            "distinctScreens": 4,
            "nodes": bg_nodes,
            "edges": _BG_EDGES,
        },
        "sprites": {
            "vocabulary": "sprites.json",
            "vocabularySize": 5,
            "oamFrames": 1000,
            "nodes": sp_nodes,
            "pairs": pairs,
        },
    }
    (sheets / "adjacency.json").write_text(json.dumps(adj) + "\n", encoding="utf-8")
    return root


# -- ADR-0170 pose sidecar fixtures -----------------------------------------
#
# One `sprNNN` group sheet whose `evidence[]` exercises both halves of the
# ADR-0168 §2 walk, so "the fallback still produces exactly today's result" is
# an assertion about the heuristic and not just about a chain:
#   * node 3's strongest edge points at (1, 0), which node 1 already holds, so
#     the occupied-slot guard refuses it and a weaker edge places it at (2, 1);
#   * node 4 is only reachable over an edge below the 25 % count floor, so it
#     stays unplaced and is absent from the layout.
_SPR000 = [0, 1, 2, 3, 4]
_SPR000_EVIDENCE = [
    {"a": 0, "b": 1, "dx": 1, "dy": 0, "count": 100},
    {"a": 1, "b": 2, "dx": 0, "dy": 1, "count": 80},
    {"a": 0, "b": 3, "dx": 1, "dy": 0, "count": 60},   # slot taken by node 1
    {"a": 2, "b": 3, "dx": 1, "dy": 0, "count": 50},
    {"a": 0, "b": 4, "dx": 0, "dy": 2, "count": 5},    # under the floor
]
_WALK_EXPECTED = {0: (0, 0), 1: (1, 0), 2: (1, 1), 3: (2, 1)}

# The same figure as the recorder actually saw it in one OAM frame: a 2x3
# silhouette, node 4 included (the walk could never reach it) and laid out
# differently from anything the pairwise offsets imply.
_POSE_TILES = {0: (0, 0), 1: (1, 0), 2: (0, 1), 3: (1, 1), 4: (0, 2)}

# The same silhouette *without* the hub node 0, for the ranking cases: a pose
# the composed set does not already contain. Seeding node 0 must be able to
# rank it, which it cannot when node 0 is one of its own members — composing
# the hub composes the whole pose, and ADR-0171 §4's "not a candidate" rule
# then applies to it.
_POSE_NO_SEED = {1: (0, 0), 2: (1, 0), 3: (0, 1), 4: (1, 1)}


def _write_spr_group(sheets, stem="spr000", nodes=None, evidence=None):
    nodes = _SPR000 if nodes is None else nodes
    cells = [_sprite_cell(i, m, 100) for i, m in enumerate(nodes)]
    _write_sheet(sheets, stem, "sprite", cells, 8, 4,
                 extra={"evidence": _SPR000_EVIDENCE if evidence is None else evidence})


def _write_poses(sheets, doc):
    (Path(sheets) / E.POSES_FILE).write_text(json.dumps(doc), encoding="utf-8")


def _poses_doc(tiles=None, extra_poses=None):
    tiles = _POSE_TILES if tiles is None else tiles
    poses = [{"id": "pose000", "frames": 412, "size": [2, 3],
              "tiles": [{"node": n, "dx": d[0], "dy": d[1]} for n, d in sorted(tiles.items())]}]
    poses.extend(extra_poses or [])
    return {"version": 1, "unit": 8, "frames": 1440, "poses": poses}


class _WalkSpy:
    """Swap `E.walk_layout` out to prove ADR-0170 §4's "does not run the walk"
    is a fact about the code path, not an inference from the output."""

    def __init__(self):
        self.calls = 0

    def __enter__(self):
        self._real = E.walk_layout

        def spy(nodes, evidence):
            self.calls += 1
            return self._real(nodes, evidence)

        E.walk_layout = spy
        return self

    def __exit__(self, *exc):
        E.walk_layout = self._real
        return False


def test_pose_sidecar_lays_the_figure_out_and_skips_the_walk():
    """ADR-0170 §4: with `poses.json` the layout is the pose's, and the
    ADR-0168 §2 walk is not run at all."""
    with tempfile.TemporaryDirectory() as td:
        root = make_pack(Path(td))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        _write_poses(sheets, _poses_doc())
        pack = E.Pack(root)
        check(pack.poses is not None, "poses.json is loaded when present")
        with _WalkSpy() as spy:
            layout, source, pose = pack.figure_layout_detail("spr000")
        check(source == "poses", "layout source is the sidecar", source)
        check(spy.calls == 0, "the evidence[] walk is not run", f"{spy.calls} call(s)")
        check(layout == _POSE_TILES, "the figure is laid out from the pose", str(layout))
        check(pose is not None and pose.id == "pose000" and pose.extent() == (2, 3),
              "the pose is reported with its extent", str(pose and pose.extent()))
        check(layout != _WALK_EXPECTED, "the pose layout is not the walk's answer")


def test_pack_without_poses_falls_back_to_todays_walk():
    """A pack recorded before ADR-0170 composes exactly as it does today: the
    ADR-0168 §2 walk, its occupied-slot guard and its count floor included."""
    with tempfile.TemporaryDirectory() as td:
        root = make_pack(Path(td))
        _write_spr_group(root / "textures" / "sheets")
        pack = E.Pack(root)
        check(pack.poses is None, "no sidecar means no poses")
        with _WalkSpy() as spy:
            layout, source, pose = pack.figure_layout_detail("spr000")
        check(source == "walk" and spy.calls == 1, "the walk runs", f"{source}/{spy.calls}")
        check(pose is None, "no pose is reported on the fallback path")
        check(layout == _WALK_EXPECTED, "the walk places the group as it does today", str(layout))
        check(4 not in layout, "a member reachable only under the count floor stays unplaced")
        # The spike is the reference implementation ADR-0168 §2 names; it and
        # the engine must be one walk, not two.
        import spike_compose_scene as S
        check(S.shape_layout(root / "textures" / "sheets", "spr000") == _WALK_EXPECTED,
              "the spike's shape_layout agrees with the engine")


def test_malformed_pose_sidecar_degrades_to_the_walk():
    """Every way the sidecar can be unusable ends in the fallback, never in an
    exception: the artist keeps the composition they can get today."""
    cases = {
        "missing poses key": {"version": 1, "unit": 8, "frames": 10},
        "empty poses list": {"version": 1, "unit": 8, "frames": 10, "poses": []},
        "unknown format version": dict(_poses_doc(), version=2),
        "not a JSON object": [1, 2, 3],
        "poses of unknown nodes only": {"version": 1, "poses": [
            {"id": "pose000", "frames": 9, "tiles": [{"node": 900, "dx": 0, "dy": 0}]}]},
        "tiles are junk": {"version": 1, "poses": [
            {"id": "pose000", "frames": 9, "tiles": [{"node": "x"}, 7, {}]}]},
    }
    for name, doc in cases.items():
        with tempfile.TemporaryDirectory() as td:
            root = make_pack(Path(td))
            sheets = root / "textures" / "sheets"
            _write_spr_group(sheets)
            _write_poses(sheets, doc)
            pack = E.Pack(root)
            check(pack.poses is None, f"unusable sidecar ({name}) reads as absent")
            check(pack.figure_layout("spr000") == _WALK_EXPECTED,
                  f"unusable sidecar ({name}) still lays the figure out by the walk")
    # Not even valid JSON.
    with tempfile.TemporaryDirectory() as td:
        root = make_pack(Path(td))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        (sheets / E.POSES_FILE).write_text("{ not json", encoding="utf-8")
        pack = E.Pack(root)
        check(pack.poses is None and pack.figure_layout("spr000") == _WALK_EXPECTED,
              "a sidecar that is not JSON reads as absent")


def test_partial_pose_sidecar_keeps_what_it_can():
    """A tile naming a node outside the sprite vocabulary is dropped, not
    trusted and not fatal — `poses.json` and `adjacency.json` are two
    projections of one stream and nothing cross-checks them (ADR-0170
    Consequences). What is left of the pose still lays the figure out."""
    with tempfile.TemporaryDirectory() as td:
        root = make_pack(Path(td))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        tiles = dict(_POSE_TILES)
        tiles[77] = (2, 2)  # not in sprites.nodes[]
        # A second entry, listed first and seen less often, so the load has to
        # re-establish ADR-0170 §1's frames-descending order to pick right.
        stale = {"id": "pose001", "frames": 3, "size": [1, 1],
                 "tiles": [{"node": 0, "dx": 0, "dy": 0}, {"node": 4, "dx": 1, "dy": 0}]}
        doc = _poses_doc(tiles=tiles, extra_poses=[stale])
        doc["poses"].reverse()
        _write_poses(sheets, doc)
        pack = E.Pack(root)
        check(pack.poses.dropped_tiles == 1, "the out-of-vocabulary tile is dropped",
              str(pack.poses.dropped_tiles))
        check([p.id for p in pack.poses.entries] == ["pose000", "pose001"],
              "entries are ordered most-seen first")
        layout, source, pose = pack.figure_layout_detail("spr000")
        check(source == "poses" and layout == _POSE_TILES,
              "the surviving tiles lay the figure out", f"{source} {layout}")
        check(77 not in layout, "the unknown node never reaches a consumer")


def test_figure_layout_edges_do_not_raise():
    """A group sheet with no cells, and an anchor no pose contains, both fall
    through to the walk rather than blowing up."""
    with tempfile.TemporaryDirectory() as td:
        root = make_pack(Path(td))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        # A pose that holds none of the group's nodes: the anchor is unknown to
        # the sidecar, so this figure has no pose and walks.
        _write_poses(sheets, {"version": 1, "poses": [
            {"id": "pose000", "frames": 40,
             "tiles": [{"node": 2, "dx": 0, "dy": 0}, {"node": 3, "dx": 1, "dy": 0}]}]})
        pack = E.Pack(root)
        check(pack.poses is not None, "the sidecar itself is fine")
        check(pack.figure_layout_detail("spr000")[1] == "walk",
              "an anchor no pose contains falls back to the walk")
        _write_spr_group(sheets, stem="spr001", nodes=[])
        check(E.Pack(root).figure_layout("spr001") == {},
              "an empty group sheet lays out as nothing")
        check(pack.group_nodes("spr000") == _SPR000, "group_nodes reads the cells in order")
        try:
            pack.figure_layout("spr999")
        except E.ComposeError as e:
            check("not readable as JSON" in str(e), "a missing group sheet is a ComposeError", str(e))
        else:
            check(False, "a missing group sheet is a ComposeError", "no raise")


def test_missing_adjacency_tells_artist_to_rebootstrap():
    with tempfile.TemporaryDirectory() as td:
        root = make_pack(Path(td))
        (root / "textures" / "sheets" / "adjacency.json").unlink()
        try:
            E.Pack(root)
        except E.ComposeError as e:
            check("re-run the bootstrap" in str(e), "missing adjacency.json names the fix", str(e))
        else:
            check(False, "missing adjacency.json names the fix", "Pack() did not raise")


def test_band_membership_uses_bottom_edge():
    with tempfile.TemporaryDirectory() as td:
        pack = E.Pack(make_pack(Path(td)))
        adj = pack.adjacency
        check(176 in adj.floors() and 128 in adj.floors(), "floors() lists quantised bottom bands",
              str(adj.floors()))
        members = adj.band_members(176)
        check(0 in members and 1 in members and 2 in members, "ground members on the 176 band", str(members))
        # The projectile stands on the ground band rarely but still does; a shape
        # whose bottom edge never reaches the band is excluded by construction.
        check(adj.sp[3].on_floor(176), "projectile touches the ground band sometimes")
        check(not any(adj.sp[m].on_floor(128) for m in (0, 1, 2)), "ground shapes never on the 128 band")


def test_screen_fixed_sprites_are_not_band_members():
    """ADR-0173 (issue #167): the HUD reaches a band by being painted across
    it. It is the most-seen shape in the pack, so it would head every
    suggestion list for every band it touches."""
    with tempfile.TemporaryDirectory() as td:
        pack = E.Pack(make_pack(Path(td)))
        adj = pack.adjacency
        check(adj.sp[5].screen_fixed, "the sidecar's screenFixed flag is read")
        check(5 not in adj.band_members(176) and 5 not in adj.band_members(128),
              "a screen-fixed shape is no band's member", str(adj.band_members(176)))
        check(192 not in adj.floors(), "a band only the HUD reaches is not a band",
              str(adj.floors()))
        check(176 in adj.floors() and 128 in adj.floors(),
              "the real bands survive the filter", str(adj.floors()))
        # The evidence is not deleted - the file still says where it was drawn.
        check(adj.sp[5].on_floor(176), "the screen-fixed shape keeps its floors[]")
        check(5 not in [c for c, _s in pack.sprite_rank(176, locked=[0])],
              "the HUD never reaches a band's ranking either")


def test_acceptance_sprite_band_ranks_ground_enemies_above_projectile():
    with tempfile.TemporaryDirectory() as td:
        pack = E.Pack(make_pack(Path(td)))
        band = 176  # the band under Ryu's bottom edge
        ranked = pack.sprite_rank(band, locked=[0])
        cells = [c for c, _ in ranked]
        check(1 in cells[:2] and 2 in cells[:2], "both ground enemies lead the recompute", str(cells))
        p = cells.index(3) if 3 in cells else None
        check(p is None or p >= max(cells.index(1), cells.index(2)),
              "projectile ranks at or below every ground enemy", f"pos {p} in {cells}")
        check(4 not in cells, "far-field shape with zero coFrames is not a candidate", str(cells))


def test_acceptance_background_recompute_places_obj_group_first():
    with tempfile.TemporaryDirectory() as td:
        pack = E.Pack(make_pack(Path(td)))
        # The seed is a metatile that obj000 groups; lock its strongest neighbour.
        seed = _OBJ000[0]
        first = pack.background_rank([seed], budget=1)[0][0]
        check(first in _OBJ000[1:], "strongest neighbour is inside the group", f"got {first}")
        locked = [seed, first]
        ranked = [c for c, _ in pack.background_rank(locked)]
        rest = [m for m in _OBJ000 if m not in locked]
        rest_pos = {m: ranked.index(m) for m in rest}
        decoy_pos = [ranked.index(m) for m in (4, 5, 6)]
        check(rest and max(rest_pos.values()) < min(decoy_pos),
              "every remaining obj000 cell ranks before any decoy",
              f"rest {rest_pos}, decoys {decoy_pos}, order {ranked}")
        check(ranked == sorted(ranked, key=lambda c: ranked.index(c)),
              "background rank is deterministic (score desc, id asc)", str(ranked))


def test_export_object_is_legal_mep_build_input():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pack = E.Pack(make_pack(root))
        out = root / "mep" / "textures" / "sheets"
        out.mkdir(parents=True)
        name = pack.export("object", [1, 2, 0], seed=0, locked=[0, 3], to_dir=out)
        check(name == "usr000", "first composition is usr000", name)
        doc = json.loads((out / f"{name}.json").read_text(encoding="utf-8"))
        check(doc["kind"] == "object" and doc["composed"] is True, "exported kind object + composed")
        check(doc["seed"] == 0 and doc["locked"] == [0, 3], "seed/locked carried", str(doc.get("locked")))
        check(len(doc["cells"]) == 3, "one cell per kept node", str(len(doc["cells"])))
        # mep_build's own loader accepts it as an ADR-0153 sheet, silently.
        docs, _ = mep_build_load(out)
        check(len(docs) == 1 and docs[0].kind == "object", "mep_build loads the composed sheet", str(len(docs)))
        # Art is on disk and not blank: each exported cell matches what the
        # engine resolved for its node (node 1 is an alias of node 0, so it
        # shares node 0's pixels — never a blank and never a wrong drawing).
        img = sheet_repaint.read_png(out / f"{name}.orig.png")
        for c, node in zip(doc["cells"], (1, 2, 0)):
            px = img.get(int(c["x"]), int(c["y"]))
            want = pack.node_art(node, sprite=False).get(0, 0)
            check(px == want, f"cell for node {node} carries its resolved art", f"{px} vs {want}")
        check(img.get(int(doc["cells"][0]["x"]), int(doc["cells"][0]["y"])) != (0, 0, 0, 0),
              "composed cell is not fully transparent")


def test_export_sprite_band_records_band_and_twin():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pack = E.Pack(make_pack(root))
        out = root / "mep" / "textures" / "sheets"
        out.mkdir(parents=True)
        name = pack.export("sprite", [0, 1, 2], seed=0, locked=[0, 1], band=176, to_dir=out)
        doc = json.loads((out / f"{name}.json").read_text(encoding="utf-8"))
        check(doc["band"] == {"bottom": 176, "tolerance": 8}, "band recorded for the sprite layer",
              str(doc.get("band")))
        check(doc["cells"][0]["count"] == 3000, "appearances carried from the sprite node")
        png = (out / f"{name}.png").read_bytes()
        orig = (out / f"{name}.orig.png").read_bytes()
        check(png == orig, "png and orig twin start byte-identical", f"{len(png)} vs {len(orig)}")


def test_node_art_never_blank_and_alias_resolves():
    with tempfile.TemporaryDirectory() as td:
        pack = E.Pack(make_pack(Path(td)))
        # Node 1 has no cell of its own: it was absorbed as an alias of cell 0
        # (F9.7). Its art must resolve to that cell's pixels, never a blank.
        art = pack.node_art(1, sprite=False)
        px = art.get(0, 0)
        want = _node_color(0)
        check(px == want, "aliased node resolves to its absorbing cell's art", f"{px} vs {want}")
        # A node no sheet shows is a screen-owned cell (ADR-0156): the engine
        # refuses rather than paste a blank.
        try:
            pack.node_art(9, sprite=False)
        except E.ComposeError as e:
            check("screen-owned" in str(e), "screen-owned node raises, never a silent blank", str(e))
        else:
            check(False, "screen-owned node raises, never a silent blank", "no ComposeError")
        # Distinct nodes give distinct art (not a shared blank/substitute).
        art_a = pack.node_art(2, sprite=False).get(0, 0)
        art_b = pack.node_art(4, sprite=False).get(0, 0)
        check(art_a != art_b, "distinct nodes carry distinct pixels", f"{art_a} vs {art_b}")


def test_screen_owned_node_resolves_via_owning_screen():
    with tempfile.TemporaryDirectory() as td:
        pack = E.Pack(make_pack(Path(td)))
        # Node 7 has no sheet cell (a captured screen owns it). Since ADR-0166
        # the adjacency sidecar names the capture, so the engine crops it from
        # backgrounds/screenNNN.orig.png at the pack's scale and reduces back
        # to 1x — here through the scale-2 capture, the first site listed.
        art = pack.node_art(7, sprite=False)
        px = art.get(0, 0)
        want = _node_color(7)
        check(px == want, "screen-owned node crops out of its owning capture", f"{px} vs {want}")
        check(art.width == 16, "screen crop is downscaled to the 1x grid unit", str(art.width))
        # Node 8 is marked resident but carries no screens[] (a stale pack).
        try:
            pack.node_art(8, sprite=False)
        except E.ComposeError as e:
            check("screen-owned" in str(e), "resident node without screens[] still raises", str(e))
        else:
            check(False, "resident node without screens[] still raises", "no ComposeError")


def test_export_rejects_unknown_kind_and_noop():
    with tempfile.TemporaryDirectory() as td:
        pack = E.Pack(make_pack(Path(td)))
        try:
            pack.export("bogus", [0, 1], seed=0, locked=[0])
        except E.ComposeError as e:
            check("must be 'object' or 'sprite'" in str(e), "unknown composed kind rejected", str(e))
        else:
            check(False, "unknown composed kind rejected", "no ComposeError")
        try:
            pack.export("object", [], seed=0, locked=[])
        except E.ComposeError as e:
            check("nothing to export" in str(e), "empty composition rejected", str(e))
        else:
            check(False, "empty composition rejected", "no ComposeError")


def test_export_twice_to_same_dir_gets_distinct_names():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pack = E.Pack(make_pack(root))
        # to_dir differs from the pack's own sheets_dir, exactly as a real save
        # into mep/ does (ADR-0165 §4) — the free-name scan must look at to_dir,
        # not the pack's own auto/ sheets. Found via a real Mega Man 3 recording
        # (F9.18 acceptance, 2026-09-07): exporting an object composition then a
        # sprite composition into the same mep/ folder both landed on usr000,
        # and the second write silently clobbered the first on disk.
        out = root / "mep" / "textures" / "sheets"
        out.mkdir(parents=True)
        name_a = pack.export("object", [0, 2], seed=0, locked=[0], to_dir=out)
        name_b = pack.export("sprite", [0, 1], seed=0, locked=[0], band=176, to_dir=out)
        check(name_a != name_b, "second export to the same to_dir gets a distinct name",
              f"{name_a} vs {name_b}")
        check((out / f"{name_a}.json").exists() and (out / f"{name_b}.json").exists(),
              "neither export's sidecar was overwritten by the other")


def mep_build_load(sheets_dir):
    """mep_build's own sheet loader, kept behind a name so the suite does not
    pretend it needs more of mep_build than the engine already imports."""
    import mep_build
    return mep_build._load_sheet_docs(Path(sheets_dir))



# -- ADR-0171: the pose is the unit of the sprite layer ----------------------


def test_pose_anchor_is_the_rarest_member():
    """ADR-0171 §5 keeps `seed`/`locked` naming nodes, so the anchor has to be
    the member that tells this silhouette apart from the character's others —
    the least-seen one, not the torso every pose shares."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_pack(Path(tmp))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        _write_poses(sheets, _poses_doc())
        pack = E.Pack(root)
        pose = pack.poses.entries[0]
        anchor = pack.pose_anchor(pose)
        # appearances: 0:3000, 1:500, 2:400, 3:900, 4:100
        check(anchor == 4, "the anchor is the pose's rarest member", f"anchor={anchor}")
        check(pack.pose_of(anchor) is pose,
              "the anchor resolves back to the pose it identifies",
              str(pack.pose_of(anchor) and pack.pose_of(anchor).id))


def test_pose_band_membership_is_the_bottom_row():
    """ADR-0171 §3: a pose stands on the band its *bottom row* stands on. Node
    3 is mostly on band 128 but sits mid-silhouette here, so the pose belongs
    to 176 (where its bottom node 4 stands) and not to 128."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_pack(Path(tmp))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        _write_poses(sheets, _poses_doc())
        pack = E.Pack(root)
        pose = pack.poses.entries[0]
        bottom = pack.pose_bottom_nodes(pose)
        check(bottom == [4], "the bottom row is the members at max(dy)", str(bottom))
        on176 = [p.id for p in pack.pose_band_members(176)]
        on128 = [p.id for p in pack.pose_band_members(128)]
        check(on176 == ["pose000"], "the pose stands on its bottom row's band", str(on176))
        check(on128 == [],
              "a member standing on another band does not drag the pose there",
              str(on128))


def test_pose_rank_scores_by_co_presence_damped_by_size():
    """ADR-0171 §4, the formula as written: sum(coFrames) / sqrt(members)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_pack(Path(tmp))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        _write_poses(sheets, _poses_doc(tiles=_POSE_NO_SEED))
        pack = E.Pack(root)
        ranked = pack.pose_rank(176, locked=[0])
        check(len(ranked) == 1, "the band's one pose is the one candidate", str(len(ranked)))
        if len(ranked) != 1:
            return
        anchor, score, pose = ranked[0]
        # coFrames against node 0: 1:480, 2:420, 3:40, 4:0 -> 940 over 4 members
        want = 940 / math.sqrt(4)
        check(anchor == 4 and abs(score - want) < 1e-9,
              "the score is the summed co-presence damped by sqrt(member count)",
              f"anchor={anchor} score={score:.3f} want={want:.3f}")
        check(pack.pose_of(anchor).id == pose.id,
              "the ranked pose is the one a reopened session resolves",
              f"{pose.id} vs {pack.pose_of(anchor).id}")


def test_pose_rank_drops_the_uncorrelated_and_collapses_one_anchor():
    """A pose that never shared a frame with the locked set is not a
    candidate, and two poses resolving to one anchor are offered once — the
    artist must not be able to pick a silhouette that reopening would not
    restore."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_pack(Path(tmp))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        # A second silhouette over the same rarest member (node 4), seen less
        # often, plus one built only from node 4 and the zero-coFrames decoy.
        twin = {"id": "pose001", "frames": 12, "size": [2, 2],
                "tiles": [{"node": n, "dx": d[0], "dy": d[1]}
                          for n, d in ((1, (0, 0)), (2, (1, 0)), (4, (0, 1)))]}
        _write_poses(sheets, _poses_doc(tiles=_POSE_NO_SEED, extra_poses=[twin]))
        pack = E.Pack(root)
        ranked = pack.pose_rank(176, locked=[0])
        anchors = [a for a, _s, _p in ranked]
        check(anchors == [4], "two poses over one anchor are one candidate", str(anchors))
        check(ranked and ranked[0][2].id == "pose000",
              "the candidate shown is the most-seen silhouette, as `pose_of` picks it",
              str(ranked and ranked[0][2].id))
        check(pack.pose_rank(176, locked=[]) == [],
              "an empty lock set ranks nothing, as for nodes", "")


def test_a_silhouette_already_composed_is_not_offered_again():
    """The counterpart of the anchor dedup, found on a real Mega Man 3 pack:
    several anchors resolve to one pose, so filtering candidates by anchor
    alone offers the artist the very picture already on the row, one cell to
    its left. Seeding node 0 composes the pose that contains it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_pack(Path(tmp))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        _write_poses(sheets, _poses_doc())  # node 0 is a member of pose000
        pack = E.Pack(root)
        check(pack.pose_of(0) is not None and pack.pose_of(0).id == "pose000",
              "the seeded node resolves to the pose it belongs to")
        check(pack.pose_rank(176, locked=[0]) == [],
              "the band's only silhouette is already composed, so nothing is offered",
              str(pack.pose_rank(176, locked=[0])))


def test_a_fused_pose_is_never_offered_as_a_figure():
    """ADR-0177 §5: an entry the recorder labelled a fusion is two figures that
    touched, so the suggestion list must not offer it. It stays reachable by
    id — the label is a filter for the ranked list, not a deletion."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_pack(Path(tmp))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        tiles = [{"node": n, "dx": d[0], "dy": d[1]} for n, d in sorted(_POSE_TILES.items())]
        fused = {"id": "pose001", "frames": 9, "size": [2, 3],
                 "fusionOf": ["pose000", "pose000"], "tiles": tiles}
        _write_poses(sheets, _poses_doc(extra_poses=[fused]))
        pack = E.Pack(root)

        by_id = {e.id: e for e in pack.poses.entries}
        check(set(by_id) == {"pose000", "pose001"},
              "both entries are read, the fused one included", str(sorted(by_id)))
        check(by_id["pose001"].fusion_of == ("pose000", "pose000"),
              "fusionOf is read as the pose ids the entry splits into",
              str(by_id["pose001"].fusion_of))
        check(by_id["pose001"].fused and not by_id["pose000"].fused,
              "only the labelled entry reads as fused",
              f'{by_id["pose001"].fused}/{by_id["pose000"].fused}')

        offered = [e.id for e in pack.pose_band_members(176)]
        check(offered == ["pose000"],
              "the band offers the figure and not the fusion", str(offered))
        check(pack.poses.by_id("pose001") is not None,
              "a fused pose is still reachable by id")


def test_a_pose_sidecar_without_fusion_labels_reads_as_before():
    """ADR-0177 §4: absent means *not classified*, and a pack recorded before
    the ADR must behave exactly as it did — no entry silently filtered."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_pack(Path(tmp))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        tiles = [{"node": n, "dx": d[0], "dy": d[1]} for n, d in sorted(_POSE_TILES.items())]
        twin = {"id": "pose001", "frames": 9, "size": [2, 3], "tiles": tiles}
        _write_poses(sheets, _poses_doc(extra_poses=[twin]))
        pack = E.Pack(root)
        check(all(not e.fused for e in pack.poses.entries),
              "no entry of a pre-ADR-0177 sidecar reads as fused")
        offered = [e.id for e in pack.pose_band_members(176)]
        check(offered == ["pose000", "pose001"],
              "both entries are still offered", str(offered))


def test_a_malformed_fusion_label_is_ignored_not_fatal():
    """The sidecar is never trusted enough to raise (ADR-0170). A `fusionOf`
    that is not a list of ids leaves the entry unclassified rather than
    dropping it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_pack(Path(tmp))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        tiles = [{"node": n, "dx": d[0], "dy": d[1]} for n, d in sorted(_POSE_TILES.items())]
        bad = {"id": "pose001", "frames": 9, "size": [2, 3],
               "fusionOf": "pose000", "tiles": tiles}
        _write_poses(sheets, _poses_doc(extra_poses=[bad]))
        pack = E.Pack(root)
        entry = pack.poses.by_id("pose001")
        check(entry is not None, "the entry survives a malformed label")
        check(entry.fusion_of == () and not entry.fused,
              "a label that is not a list of ids reads as unclassified",
              str(entry.fusion_of))


def test_pose_cells_keep_the_silhouette_and_never_repeat_a_node():
    """ADR-0171 §5: composing poses changes which cells land where, not the
    file. A node already placed is not emitted twice — `mep_build.py` fans a
    painted cell back out by its tile key, so two cells on one key would be
    two answers to the same question."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_pack(Path(tmp))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        _write_poses(sheets, _poses_doc())
        pack = E.Pack(root)
        cells = pack.pose_cells([4])
        placed = {n: (cx, cy) for n, cx, cy in cells}
        # Node 4 is the fixture's vocabulary node that no sheet draws — the
        # real mismatch S10.a hit (poses.json indexes 288 nodes, the sheet drew
        # 241). It is skipped, and the rest keeps its offsets.
        drawn = {n: d for n, d in _POSE_TILES.items() if n != 4}
        check(placed == drawn, "the pose keeps its own shape on the sheet", str(placed))
        check(4 not in placed, "a member no sheet draws is not exported", str(placed))
        twice = pack.pose_cells([4, 4])
        nodes = [n for n, _cx, _cy in twice]
        check(len(nodes) == len(set(nodes)), "a node is never emitted twice", str(nodes))


def test_pose_placements_reach_the_exported_sheet():
    """The composed sprite sheet puts each cell where the pose put it, and is
    still ordinary `mep_build.py` input with `seed`/`locked` naming nodes."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_pack(Path(tmp))
        sheets = root / "textures" / "sheets"
        _write_spr_group(sheets)
        _write_poses(sheets, _poses_doc())
        pack = E.Pack(root)
        placements = pack.pose_cells([4])
        nodes = [n for n, _cx, _cy in placements]
        name = pack.export("sprite", nodes, seed=4, locked=[], band=176,
                           to_dir=sheets, placements=placements)
        doc = json.loads((sheets / f"{name}.json").read_text())
        by_node = {c["metatile"]: (c["x"], c["y"]) for c in doc["cells"]}
        stride = 8 + E.GUTTER
        want = {n: (E.GUTTER + dx * stride, E.GUTTER + dy * stride)
                for n, (dx, dy) in _POSE_TILES.items() if n != 4}
        check(by_node == want, "every cell is at its pose offset", str(by_node))
        check(doc["seed"] == 4 and doc["locked"] == [],
              "seed and locked still name nodes (ADR-0171 §5)", str(doc.get("seed")))
        docs, _ = mep_build_load(sheets)
        check(any(d.kind == "sprite" for d in docs),
              "the composed pose sheet is ordinary mep_build input", str(len(docs)))


def test_pack_without_poses_ranks_nodes_as_before():
    """The fallback rung: no sidecar, no pose candidates, and `sprite_rank`
    still answers exactly as it does today."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_pack(Path(tmp))
        pack = E.Pack(root)
        check(pack.pose_rank(176, locked=[0]) == [],
              "a pack with no sidecar offers no pose candidates", "")
        check(pack.pose_band_members(176) == [],
              "and no band poses", "")
        nodes = [n for n, _co in pack.sprite_rank(176, locked=[0])]
        check(nodes[:2] == [1, 2], "the node ranking is untouched", str(nodes))


def test_export_writes_the_sheet_at_the_packs_scale():
    """A bootstrap pack is emitted upscaled (4x sheet, 1x twin). A composed
    sheet written at 1x makes `mep_build.py build` reject the whole pack -
    "all sheets of a pack share one <scale>" - so the compose -> export ->
    paint -> rebuild loop never closes on a real pack. Issue #169."""
    with tempfile.TemporaryDirectory() as td:
        root = make_pack(Path(td), scale=4)
        pack = E.Pack(root)
        check(pack.scale == 4, "the pack reports its sheets' scale", str(pack.scale))
        name = pack.export("object", [0, 2, 3], seed=0, locked=[2, 3])
        sheets = root / "textures" / "sheets"
        painted = sheet_repaint.read_png(sheets / f"{name}.png")
        twin = sheet_repaint.read_png(sheets / f"{name}.orig.png")
        check(painted.width == twin.width * 4 and painted.height == twin.height * 4,
              "the sheet is written at the pack's scale, the twin at 1x",
              f"{painted.width}x{painted.height} vs {twin.width}x{twin.height}")
        doc = json.loads((sheets / f"{name}.json").read_text())
        logical_w = doc["columns"] * (doc["gridUnit"] + doc["gutter"]) + doc["gutter"]
        check(painted.width == logical_w * 4,
              "the sidecar geometry stays 1x, so mep_build derives scale 4",
              f"{painted.width} vs {logical_w}")
        check(all(int(c["x"]) % 1 == 0 and int(c["x"]) < logical_w for c in doc["cells"]),
              "cell records stay inside the 1x sheet the sidecar describes")
        # The pixels come from the painted sheet itself (the marker the fixture
        # stamps on it), not from a blow-up of the twin.
        cell0 = doc["cells"][0]
        mark = painted.get(cell0["x"] * 4, cell0["y"] * 4)
        source = sheet_repaint.read_png(sheets / "metatiles.png").get(
            int(_first_metatile_xy(doc, sheets)[0]) * 4, int(_first_metatile_xy(doc, sheets)[1]) * 4)
        check(mark == source, "composed art is cropped from the painted sheet", f"{mark} vs {source}")


def _first_metatile_xy(doc, sheets):
    """Where the first composed cell's node lives on the metatiles sheet."""
    node = doc["cells"][0]["metatile"]
    src = json.loads((sheets / "metatiles.json").read_text())
    for c in src["cells"]:
        if c["metatile"] == node:
            return c["x"], c["y"]
    raise AssertionError(f"node {node} is not on the metatiles sheet")


def test_a_1x_pack_still_exports_a_1x_pair():
    """The old behaviour is the special case, not a second code path."""
    with tempfile.TemporaryDirectory() as td:
        root = make_pack(Path(td))
        pack = E.Pack(root)
        check(pack.scale == 1, "a 1x pack reports scale 1", str(pack.scale))
        name = pack.export("object", [0, 2], seed=0, locked=[2])
        sheets = root / "textures" / "sheets"
        a = sheet_repaint.read_png(sheets / f"{name}.png")
        b = sheet_repaint.read_png(sheets / f"{name}.orig.png")
        check((a.width, a.height) == (b.width, b.height) and a.px == b.px,
              "sheet and twin start identical at 1x", f"{a.width}x{a.height} vs {b.width}x{b.height}")


def main():
    tests = [
        test_missing_adjacency_tells_artist_to_rebootstrap,
        test_band_membership_uses_bottom_edge,
    test_screen_fixed_sprites_are_not_band_members,
        test_acceptance_sprite_band_ranks_ground_enemies_above_projectile,
        test_acceptance_background_recompute_places_obj_group_first,
        test_export_object_is_legal_mep_build_input,
        test_export_sprite_band_records_band_and_twin,
        test_node_art_never_blank_and_alias_resolves,
        test_screen_owned_node_resolves_via_owning_screen,
        test_export_rejects_unknown_kind_and_noop,
        test_export_twice_to_same_dir_gets_distinct_names,
        test_pose_sidecar_lays_the_figure_out_and_skips_the_walk,
        test_pack_without_poses_falls_back_to_todays_walk,
        test_malformed_pose_sidecar_degrades_to_the_walk,
        test_partial_pose_sidecar_keeps_what_it_can,
        test_figure_layout_edges_do_not_raise,
        test_pose_anchor_is_the_rarest_member,
        test_pose_band_membership_is_the_bottom_row,
        test_pose_rank_scores_by_co_presence_damped_by_size,
        test_pose_rank_drops_the_uncorrelated_and_collapses_one_anchor,
        test_a_silhouette_already_composed_is_not_offered_again,
        test_a_fused_pose_is_never_offered_as_a_figure,
        test_a_pose_sidecar_without_fusion_labels_reads_as_before,
        test_a_malformed_fusion_label_is_ignored_not_fatal,
        test_pose_cells_keep_the_silhouette_and_never_repeat_a_node,
        test_pose_placements_reach_the_exported_sheet,
        test_pack_without_poses_ranks_nodes_as_before,
        test_export_writes_the_sheet_at_the_packs_scale,
        test_a_1x_pack_still_exports_a_1x_pair,
    ]
    for t in tests:
        t()
    print(f"\n{len(tests) - len(_FAILURES)}/{len(tests)} cases passed")
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
