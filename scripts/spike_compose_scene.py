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
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_engine as E  # noqa: E402
import sheet_repaint as SR  # noqa: E402
from compose_viewmodel import ComposeViewModel  # noqa: E402

SCREEN_W, SCREEN_H = 256, 240

#A sprite tile's transparent pixels carry a leftover RGB under a zero alpha,
#and `Image.paste` is a raw row copy, so pasting a character over a scene
#stamps that leftover as an opaque box. Every sprite paste in this file goes
#through the alpha-aware version instead.
_ALPHA_CUTOFF = 128

#How hard a background node's score is damped per cell it already occupies.
#See `fill_background`.
_REUSE_DAMPING = 0.35

#Jaccard overlap between two composed screens' node sets above which the
#second one is redundant on the board. See `seed_candidates`.
_PANEL_OVERLAP = 0.5

#Share of the best candidate's perplexity below which a composed screen is too
#empty to be worth a panel. See `seed_candidates`.
_PANEL_SCORE_FLOOR = 0.5


def paste_alpha(dst, src, x, y):
    for row in range(src.height):
        for col in range(src.width):
            px = src.get(col, row)
            if px[3] < _ALPHA_CUTOFF:
                continue
            tx, ty = x + col, y + row
            if 0 <= tx < dst.width and 0 <= ty < dst.height:
                dst.set(tx, ty, px)


# -- sprite shapes: a `sprNNN` group reassembled into one character ----------

def shape_layout(sheets_dir: Path, stem: str, pack: E.Pack = None):
    """Positions, in 8px tile units, of every node of a `sprNNN` figure.

    Two sources, and which one applies is ADR-0170 §4's rule, implemented in
    `compose_engine`: a pack that carries `sheets/poses.json` takes the layout
    from the pose the figure's anchor node appears in — a silhouette the
    recorder actually saw in one OAM frame — and does not run the ADR-0168 §2
    `evidence[]` walk. A pack recorded before that sidecar (every pack on disk
    today) walks the group sheet's offsets as it always has.

    `pack` is optional only so the old call shape keeps working; without it
    there is no pack to read the sidecar from and the walk is all there is.
    """
    if pack is not None:
        return pack.figure_layout(stem)
    doc = json.loads((sheets_dir / f"{stem}.json").read_text(encoding="utf-8"))
    nodes = [c["metatile"] for c in doc["cells"]]
    return E.walk_layout(nodes, doc.get("evidence"))


def shape_image(pack: E.Pack, sheets_dir: Path, stem: str):
    """One `sprNNN` figure drawn as the character it is, 1x, tightly cropped.
    Its tiles are the pose's when the pack has one, the group's otherwise."""
    pos = shape_layout(sheets_dir, stem, pack)
    if not pos:
        return None
    x0 = min(p[0] for p in pos.values())
    y0 = min(p[1] for p in pos.values())
    w = (max(p[0] for p in pos.values()) - x0 + 1) * 8
    h = (max(p[1] for p in pos.values()) - y0 + 1) * 8
    img = SR.Image(w, h)
    for node, (x, y) in sorted(pos.items()):
        try:
            paste_alpha(img, pack.node_art(node, sprite=True), (x - x0) * 8, (y - y0) * 8)
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


def fill_perplexity(grid):
    """Effective vocabulary of a filled screen: `exp(H)` over the node counts.

    Counting *distinct* nodes was the first attempt and it picks the wrong
    seed: the title-screen logo tiles a whole screen with one glyph plus a
    scattering of neighbours, which scores high on distinctness while looking
    like wallpaper. Perplexity asks the honest question instead — how many
    nodes is this screen *effectively* made of — so one node covering most
    cells is penalised however many rare companions it drags along."""
    counts = {}
    total = 0
    for row in grid:
        for node in row:
            if node is None:
                continue
            counts[node] = counts.get(node, 0) + 1
            total += 1
    if not total:
        return 0.0
    h = 0.0
    for c in counts.values():
        p = c / total
        h -= p * math.log(p)
    return math.exp(h)


def fill_background(pack: E.Pack, seed: int, cols: int, rows: int):
    """Greedily fill a `cols` x `rows` metatile grid from `seed`.

    `background_rank` collapses direction to rank a flat list; a screen needs
    the direction kept, so each cell is scored against the two already-placed
    neighbours that constrain it — the one to its west (an `E` edge) and the
    one to its north (an `S` edge) — using the same conditional mass ADR-0164
    persists. Deterministic: best score, ties by node id.

    Taking the plain argmax at every cell was the first version and it
    collapses: the single most likely successor of a sky tile is another sky
    tile, so the screen fills with one node and the level's structure never
    appears. Reuse is therefore damped — a node's score is divided by how many
    cells it already occupies — which keeps the choice deterministic while
    letting the second- and third-most-likely neighbours through. The damping
    strength is a judgement call, not a measured constant."""
    adj = pack.adjacency
    grid = [[None] * cols for _ in range(rows)]
    grid[0][0] = seed
    vocab = list(adj.bg.keys())
    used = {seed: 1}

    def score(cand, west, north):
        s = 0.0
        for a, direction in ((west, "E"), (north, "S")):
            if a is None:
                continue
            out = adj.out_degree(a, direction)
            if out:
                s += adj.edge_count(a, cand, direction) / out
        return s / (1.0 + _REUSE_DAMPING * used.get(cand, 0))

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
            pick = best if best_s > 0 else seed
            grid[y][x] = pick
            used[pick] = used.get(pick, 0) + 1
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


# -- the artist board -------------------------------------------------------

def seed_candidates(pack: E.Pack, members, cols, rows, want=6):
    """The seeds worth showing an artist, best-scoring first.

    Two filters before the score, both learned the hard way. Flat nodes are
    dropped (`is_flat`): a sky tile fills a screen with nothing. Rare nodes are
    dropped too — a node seen a handful of times has a sharp, confident-looking
    successor distribution built on almost no evidence, and it wins the score
    while composing a screen out of noise. What is left is the game's bulk art,
    ranked by `fill_perplexity`.

    No single winner is returned, and that is the finding, not a shortcut: on a
    real recording the candidates split into two families - the game's menu
    screens, which are static and so have the crispest adjacency evidence in
    the whole pack, and its levels. Nothing in `adjacency.json` says which is
    which, and picking for the artist would just be guessing on their behalf.
    ADR-0164's editor already puts the seed in their hands; this board is the
    same choice, laid out so it can be made by eye.

    Which is why the panels are picked for spread, not for score alone. Two
    seeds a few cells apart in the same region walk into the same neighbours
    and compose the same screen twice; six near-identical panels are not a
    choice. A candidate is kept only when its vocabulary overlaps every panel
    already taken by less than `_PANEL_OVERLAP`."""
    bg = pack.adjacency.bg
    supported = sorted((n for n, _s, _c in members if n in bg),
                       key=lambda n: (-bg[n].count, n))
    floor_at = max(1, len(supported) // 3)
    pool = supported[:floor_at] if len(supported) > 12 else supported
    scored = []
    for node in pool:
        try:
            if is_flat(pack.node_art(node, sprite=False)):
                continue
        except E.ComposeError:
            continue
        grid = fill_background(pack, node, cols, rows)
        scored.append((fill_perplexity(grid), node, grid))
    scored.sort(key=lambda t: (-t[0], t[1]))

    #A screen whose fill collapses to a couple of nodes is a blank panel: the
    #diversity rule would still admit it, precisely because it looks like
    #nothing else on the board. Judge it against the best candidate instead.
    if scored:
        keep_at = scored[0][0] * _PANEL_SCORE_FLOOR
        scored = [e for e in scored if e[0] >= keep_at]

    picked, seen = [], []
    for entry in scored:
        vocab = {n for row in entry[2] for n in row}
        if any(len(vocab & other) / len(vocab | other) >= _PANEL_OVERLAP
               for other in seen):
            continue
        picked.append(entry)
        seen.append(vocab)
        if len(picked) == want:
            break
    return picked


def draw_board(pack: E.Pack, panels, figures, unit, cols=3, gap=6):
    """Candidate scenes in a grid, each with the reassembled figures standing
    on its floor, over a strip of the same figures on their own."""
    cols = min(cols, len(panels))
    rows = (len(panels) + cols - 1) // cols
    strip_h = max((f.height for _stem, f in figures), default=0) + gap * 2
    board = SR.Image(cols * (SCREEN_W + gap) + gap,
                     rows * (SCREEN_H + gap) + gap + strip_h)
    for i, (_score, _node, grid) in enumerate(panels):
        panel = draw_background(pack, grid, unit)
        x = unit
        floor_y = SCREEN_H - 2 * unit
        for _stem, fig in figures:
            if x + fig.width > SCREEN_W - unit:
                break
            paste_alpha(panel, fig, x, floor_y - fig.height)
            x += fig.width + unit
        board.paste(panel, gap + (i % cols) * (SCREEN_W + gap),
                    gap + (i // cols) * (SCREEN_H + gap))
    x = gap
    y = rows * (SCREEN_H + gap) + gap
    for _stem, fig in figures:
        paste_alpha(board, fig, x, y + strip_h - gap - fig.height)
        x += fig.width + gap
    return board


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
    panels = seed_candidates(pack, vm.bg_members, cols, rows)
    if not panels:
        raise E.ComposeError("no seed candidate survived the flat/rare filters")
    seed = panels[0][1]
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
        paste_alpha(scene, img, x, floor_y - img.height)
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

    # 5. The artist's board. Automatic seed choice is not decidable from the
    #    recording (see `seed_candidates`), so every surviving candidate is
    #    drawn side by side and the choice stays with the artist.
    board = draw_board(pack, panels, shapes, unit)
    board_path = out_path.with_name("spike-board.png")
    SR.write_png(board_path, board.upscale(2))
    ids = ", ".join(f"#{node} (H={score:.1f})" for score, node, _g in panels)
    print(f"board: {board_path} - panels in reading order: {ids}")
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
