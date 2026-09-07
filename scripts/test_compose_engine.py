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


def _write_sheet(dirpath, stem, kind, cells, unit, columns, extra=None):
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
    sheet_repaint.write_png(dirpath / f"{stem}.png", canvas)
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


def make_pack(root: Path, with_obj_sheet: bool = True):
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
    _write_sheet(sheets, "metatiles", "metatiles", cells, 16, 4)
    # Object sheet: the group whose members the acceptance test must re-rank
    # first after a seed + lock.
    if with_obj_sheet:
        obj_cells = [_bg_cell(i, m, 100, context="scene") for i, m in enumerate(_OBJ000)]
        _write_sheet(sheets, "obj000", "object", obj_cells, 16, 4)
    # Sprite vocabulary: nodes 0..3 have art (Ryu, two ground enemies, a
    # projectile); node 4 is a far-field decoy with no sheet art.
    sprite_cells = [_sprite_cell(idx, m, (3000, 500, 400, 900)[idx]) for idx, m in enumerate((0, 1, 2, 3))]
    _write_sheet(sheets, "sprites", "sprites", sprite_cells, 8, 4)

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


def main():
    tests = [
        test_missing_adjacency_tells_artist_to_rebootstrap,
        test_band_membership_uses_bottom_edge,
        test_acceptance_sprite_band_ranks_ground_enemies_above_projectile,
        test_acceptance_background_recompute_places_obj_group_first,
        test_export_object_is_legal_mep_build_input,
        test_export_sprite_band_records_band_and_twin,
        test_node_art_never_blank_and_alias_resolves,
        test_screen_owned_node_resolves_via_owning_screen,
        test_export_rejects_unknown_kind_and_noop,
        test_export_twice_to_same_dir_gets_distinct_names,
    ]
    for t in tests:
        t()
    print(f"\n{len(tests) - len(_FAILURES)}/{len(tests)} cases passed")
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
