"""Spike: prove the composition concept end to end by rendering a real scene.

Why this exists
---------------
The composition editor (ADR-0165, F9.18) currently composes at *node*
granularity, and the human panel's verdict on it was "everything comes out
striped". This spike shows why, and what the composable unit actually is:

  * A background node is a 16x16 metatile — a self-contained piece of art.
    Composing those side by side is legible, and `Pack.background_rank`'s
    directional evidence (ADR-0164 §5) is enough to fill a whole screen
    coherently, not just to rank a flat list.
  * A *sprite* node is a single 8x8 OAM tile — a fragment of a character,
    never a character. A row of sprite nodes is therefore a row of unrelated
    8x8 slivers, which is exactly the striped noise the panel saw. The whole
    character is the `sprNNN` group, and the group sheet's `evidence[]`
    carries the `dx`/`dy` each tile sits at relative to its partners, so the
    character can be reassembled exactly.

The spike drives `ComposeViewModel` (the MVVM ViewModel) for all state — seed,
lock, rank, band — and adds only the two rendering steps the editor is
missing: a directional background fill and a `sprNNN` shape assembly. It
writes one PNG so the result can be judged by eye.

Run:  python3 scripts/spike_compose_scene.py <pack folder> [-o out.png]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_engine as E  # noqa: E402
import sheet_repaint as SR  # noqa: E402
from compose_viewmodel import ComposeViewModel  # noqa: E402

SCREEN_W, SCREEN_H = 256, 240


# -- sprite shapes: a `sprNNN` group reassembled into one character ----------

def shape_layout(sheets_dir: Path, stem: str):
    """Positions, in 8px tile units, of every node of a `sprNNN` group.

    The group sheet records one `evidence` entry per ordered tile pair with
    the `dx`/`dy` between them, so the layout is recovered by walking those
    offsets out from an anchor. Edges are taken most-observed first and a tile
    is only placed on a free slot: a group spans several animation frames, and
    a weak edge from another frame would otherwise stack two poses on top of
    each other."""
    doc = json.loads((sheets_dir / f"{stem}.json").read_text(encoding="utf-8"))
    nodes = [c["metatile"] for c in doc["cells"]]
    if not nodes:
        return {}
    edges = sorted(doc.get("evidence", []), key=lambda e: -e.get("count", 0))
    pos = {nodes[0]: (0, 0)}
    taken = {(0, 0)}
    progress = True
    while progress:
        progress = False
        for e in edges:
            a, b, dx, dy = e["a"], e["b"], e["dx"], e["dy"]
            if a in pos and b not in pos:
                cand = (pos[a][0] + dx, pos[a][1] + dy)
                who = b
            elif b in pos and a not in pos:
                cand = (pos[b][0] - dx, pos[b][1] - dy)
                who = a
            else:
                continue
            if cand in taken:
                continue
            pos[who] = cand
            taken.add(cand)
            progress = True
    return pos


def shape_image(pack: E.Pack, sheets_dir: Path, stem: str):
    """One `sprNNN` group drawn as the character it is, 1x, tightly cropped."""
    pos = shape_layout(sheets_dir, stem)
    if not pos:
        return None
    x0 = min(p[0] for p in pos.values())
    y0 = min(p[1] for p in pos.values())
    w = (max(p[0] for p in pos.values()) - x0 + 1) * 8
    h = (max(p[1] for p in pos.values()) - y0 + 1) * 8
    img = SR.Image(w, h)
    for node, (x, y) in sorted(pos.items()):
        try:
            img.paste(pack.node_art(node, sprite=True), (x - x0) * 8, (y - y0) * 8)
        except E.ComposeError:
            continue  # a tile no sheet shows: skip it, never blank the shape
    return img


def sprite_group_stems(sheets_dir: Path):
    return sorted(p.stem for p in sheets_dir.glob("spr[0-9][0-9][0-9].json"))


# -- background: a whole screen filled from the directional evidence ---------

def is_flat(img):
    """True when a node's art is a single colour — a filler/blank metatile.

    The most-*seen* background node is almost always one of these (a sky or a
    black backing tile fills most of most screens), so seeding a scene with it
    fills the screen with nothing. A composition seed has to be art."""
    if img is None or img.width == 0:
        return True
    first = img.get(0, 0)
    return all(img.get(x, y) == first for y in range(img.height) for x in range(img.width))


def pick_seed(pack: E.Pack, members, cols, rows, budget=60):
    """The seed whose fill is the richest scene, among the most-seen art nodes.

    Frequency alone is a bad seed criterion twice over: the top node is a flat
    filler, and the next ones are title-screen art whose evidence only ever
    leads back to itself, so the fill degenerates into one tile repeated. The
    honest criterion is the outcome — run the fill and keep the seed that
    lands the most distinct nodes on screen. Ties by node id, so the pick is
    deterministic."""
    best, best_score = None, -1
    for node, _sheet, _cell in members[:budget]:
        try:
            if is_flat(pack.node_art(node, sprite=False)):
                continue
        except E.ComposeError:
            continue
        grid = fill_background(pack, node, cols, rows)
        distinct = len({n for row in grid for n in row})
        if distinct > best_score:
            best, best_score = node, distinct
    return best if best is not None else members[0][0]


def fill_background(pack: E.Pack, seed: int, cols: int, rows: int):
    """Greedily fill a `cols` x `rows` metatile grid from `seed`.

    `background_rank` collapses direction to rank a flat list; a screen needs
    the direction kept, so each cell is scored against the two already-placed
    neighbours that constrain it — the one to its west (an `E` edge) and the
    one to its north (an `S` edge) — using the same conditional mass ADR-0164
    persists. Deterministic: best score, ties by node id."""
    adj = pack.adjacency
    grid = [[None] * cols for _ in range(rows)]
    grid[0][0] = seed
    vocab = list(adj.bg.keys())

    def score(cand, west, north):
        s = 0.0
        for a, direction in ((west, "E"), (north, "S")):
            if a is None:
                continue
            out = adj.out_degree(a, direction)
            if out:
                s += adj.edge_count(a, cand, direction) / out
        return s

    for y in range(rows):
        for x in range(cols):
            if grid[y][x] is not None:
                continue
            west = grid[y][x - 1] if x else None
            north = grid[y - 1][x] if y else None
            best, best_s = None, -1.0
            for cand in vocab:
                s = score(cand, west, north)
                if s > best_s:
                    best, best_s = cand, s
            grid[y][x] = best if best_s > 0 else seed
    return grid


def draw_background(pack: E.Pack, grid, unit: int):
    img = SR.Image(len(grid[0]) * unit, len(grid) * unit)
    for y, row in enumerate(grid):
        for x, node in enumerate(row):
            if node is None:
                continue
            try:
                img.paste(pack.node_art(node, sprite=False), x * unit, y * unit)
            except E.ComposeError:
                continue
    return img


# -- the two sprite units, side by side --------------------------------------

def draw_unit_comparison(pack: E.Pack, sheets_dir: Path, band_nodes, stems, gap=4):
    """Top row: sprite *nodes*, the unit the editor composes today. Bottom
    row: `sprNNN` groups reassembled, the unit a scene is actually made of.
    The top row is the striped noise; the bottom row is characters."""
    top = []
    for node in band_nodes[:14]:
        try:
            top.append(pack.node_art(node, sprite=True))
        except E.ComposeError:
            continue
    bottom = [img for img in (shape_image(pack, sheets_dir, s) for s in stems[:6])
              if img is not None]
    top_w = sum(i.width + gap for i in top)
    bot_w = sum(i.width + gap for i in bottom)
    top_h = max((i.height for i in top), default=0)
    bot_h = max((i.height for i in bottom), default=0)
    img = SR.Image(max(top_w, bot_w), top_h + gap * 3 + bot_h)
    x = 0
    for i in top:
        img.paste(i, x, 0)
        x += i.width + gap
    x = 0
    for i in bottom:
        img.paste(i, x, top_h + gap * 3 + (bot_h - i.height))
        x += i.width + gap
    return img


# -- the scene --------------------------------------------------------------

def build_scene(folder: Path, out_path: Path):
    vm = ComposeViewModel()
    print(vm.load(folder))
    pack = vm.pack
    sheets_dir = pack.sheets_dir
    unit = pack.adjacency.grid_unit

    # 1. Background — driven through the ViewModel exactly as the editor does:
    #    pick the most-seen node as the seed, then lock the top suggestions so
    #    the exported composition is the same one this scene draws.
    cols, rows = SCREEN_W // unit, SCREEN_H // unit
    seed = pick_seed(pack, vm.bg_members, cols, rows)
    vm.seed_object(seed)
    ranked = vm.background_rank()
    for node, _score in ranked[:8]:
        vm.lock(node, "object")
    print(f"background: seed #{seed}, {len(vm.locked_list())} locked, "
          f"{len(ranked)} ranked candidates")

    grid = fill_background(pack, seed, cols, rows)
    scene = draw_background(pack, grid, unit)
    distinct = len({n for row in grid for n in row})
    print(f"background: {cols}x{rows} cells filled, {distinct} distinct nodes")

    # 2. Sprites — the composable unit is the `sprNNN` group, not the node.
    #    Reassemble the biggest groups and stand them on the scene's floor.
    stems = sprite_group_stems(sheets_dir)
    shapes = []
    for stem in stems:
        img = shape_image(pack, sheets_dir, stem)
        if img is not None and img.width >= 16 and img.height >= 16:
            shapes.append((stem, img))
    shapes.sort(key=lambda s: -(s[1].width * s[1].height))
    shapes = shapes[:4]

    floor_y = SCREEN_H - 2 * unit
    x = unit
    placed = []
    for stem, img in shapes:
        if x + img.width > SCREEN_W - unit:
            break
        scene.paste(img, x, floor_y - img.height)
        placed.append(f"{stem} ({img.width}x{img.height})")
        x += img.width + unit
    print(f"sprites: assembled {len(placed)} shapes -> {', '.join(placed)}")

    # 3. Export the background composition through the ViewModel, proving the
    #    scene and the exported sheet come from the same state.
    out_dir = out_path.parent / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = vm.export(out_dir)
    print(f"exported composition: {out_dir / (name + '.png')}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    SR.write_png(out_path, scene.upscale(2))
    print(f"scene: {out_path} ({SCREEN_W * 2}x{SCREEN_H * 2})")

    # 4. The side-by-side that explains the panel's "everything is striped".
    band = vm.bands()
    vm.set_band(band[-1] if band else None)
    cmp_img = draw_unit_comparison(pack, sheets_dir, vm.band_members(), stems)
    cmp_path = out_path.with_name("spike-units.png")
    SR.write_png(cmp_path, cmp_img.upscale(3))
    print(f"units: {cmp_path} (top row = sprite nodes, bottom row = sprNNN shapes)")
    return scene


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pack", type=Path, help="pack folder (or its textures/sheets)")
    ap.add_argument("-o", "--out", type=Path, default=Path("runs/spike-sheets/spike-scene.png"))
    args = ap.parse_args(argv)
    try:
        build_scene(args.pack, args.out)
    except E.ComposeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
