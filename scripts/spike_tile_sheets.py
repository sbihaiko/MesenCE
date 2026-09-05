#!/usr/bin/env python3
"""Spike (2026-09-04): artist-legible sheets from a bootstrap grid dump.

Input: the text file written by HdPackBuilder::OnFrameEnd when
MESEN_SPIKE_GRID_DUMP is set (one `F <n>` line per frame, `K <id> <tiledata>
<palette>` on first sight of a tile, then `<x> <y> <id>` per background run on
every 8th scanline).

What it prototypes, offline, against real play data:
  1. metatile vocabulary: 16x16 blocks (2x2 tiles) aligned to the attribute
     grid, with scroll compensation inferred per frame;
  2. object grouping by *mutual predictability* between adjacent metatiles
     (P(B east of A) and P(A west of B) both high) instead of F5.4e's raw
     "seen together >= 2" union-find - the baseline is computed too, so the
     collapse into one giant component is measurable;
  3. screen stitching: stable screens linked by the scroll direction observed
     between them, laid out on a grid like the artist's overworld.png.

Outputs (in --out): frames/, metatiles.png (vocabulary contact sheet),
objects/objNNN.png, baseline_vs_pmi.txt, stitched.png, report.txt.
Not a product feature: no hires.txt is emitted.
"""
import argparse
import collections
import os
import sys

from PIL import Image, ImageDraw

NES_PALETTE = [
    0x666666, 0x002A88, 0x1412A7, 0x3B00A4, 0x5C007E, 0x6E0040, 0x6C0600, 0x561D00,
    0x333500, 0x0B4800, 0x005200, 0x004F08, 0x00404D, 0x000000, 0x000000, 0x000000,
    0xADADAD, 0x155FD9, 0x4240FF, 0x7527FE, 0xA01ACC, 0xB71E7B, 0xB53120, 0x994E00,
    0x6B6D00, 0x388700, 0x0C9300, 0x008F32, 0x007C8D, 0x000000, 0x000000, 0x000000,
    0xFFFEFF, 0x64B0FF, 0x9290FF, 0xC676FF, 0xF36AFF, 0xFE6ECC, 0xFE8170, 0xEA9E22,
    0xBCBE00, 0x88D800, 0x5CE430, 0x45E082, 0x48CDDE, 0x4F4F4F, 0x000000, 0x000000,
    0xFFFEFF, 0xC0DFFF, 0xD3D2FF, 0xE8C8FF, 0xFBC2FF, 0xFEC4EA, 0xFECCC5, 0xF7D8A5,
    0xE4E594, 0xCFEF96, 0xBDF4AB, 0xB3F3CC, 0xB5EBF2, 0xB8B8B8, 0x000000, 0x000000,
]


class Tile:
    __slots__ = ("id", "data", "palette", "shape", "pixels")

    def __init__(self, tid, data_hex, pal_hex):
        self.id = tid
        self.data = bytes.fromhex(data_hex)
        self.palette = int(pal_hex, 16)
        self.shape = self.data  # palette-agnostic identity
        self.pixels = None

    def rgb(self):
        """8x8 RGB tuples. PaletteColors byte order: [31:24]=bg color 0, [23:16]=c1, [15:8]=c2, [7:0]=c3."""
        if self.pixels is None:
            cols = [(self.palette >> ((3 - c) * 8)) & 0x3F for c in range(4)]
            px = []
            for y in range(8):
                lo, hi = self.data[y], self.data[y + 8]
                for x in range(8):
                    bit = 7 - x
                    c = ((lo >> bit) & 1) | (((hi >> bit) & 1) << 1)
                    v = NES_PALETTE[cols[c]]
                    px.append(((v >> 16) & 255, (v >> 8) & 255, v & 255))
            self.pixels = px
        return self.pixels


def parse_dump(path):
    tiles = {}
    frames = []  # list of (frame_no, rows) with rows: {y: [(x, id), ...]}
    cur = None
    with open(path) as f:
        for line in f:
            if line.startswith("F "):
                cur = (int(line[2:]), collections.defaultdict(list))
                frames.append(cur)
            elif line.startswith("K "):
                _, tid, data, pal = line.split()
                tiles[int(tid)] = Tile(int(tid), data, pal)
            elif cur is not None:
                x, y, tid = line.split()
                cur[1][int(y)].append((int(x), int(tid)))
    return tiles, frames


HUD_BOTTOM = 0  # set from --hud-rows-bottom; cell rows >= 30-HUD_BOTTOM are dropped


def frame_grid(rows, tiles):
    """Return (fine_x, grid) where grid[(col,row)] = tile id, cols aligned to the
    inferred fine x scroll (run starts sit on tile boundaries)."""
    starts = collections.Counter()
    for y, runs in rows.items():
        for x, _ in runs:
            if x != 0:
                starts[x % 8] += 1
    fine = starts.most_common(1)[0][0] if starts else 0
    grid = {}
    for y, runs in rows.items():
        runs = sorted(runs)
        row = y // 8
        for i, (x, tid) in enumerate(runs):
            x_end = runs[i + 1][0] if i + 1 < len(runs) else 256
            # first aligned cell origin at or after x
            cx = x if (x - fine) % 8 == 0 else x + (8 - (x - fine) % 8)
            while cx < x_end:
                if cx + 8 <= 256 and row < 30 - HUD_BOTTOM:
                    grid[((cx - fine) // 8, row)] = tid
                cx += 8
    return fine, grid


def render_grid(grid, tiles, fine=0, scale=1):
    img = Image.new("RGB", (256, 240), (0, 0, 0))
    px = img.load()
    for (col, row), tid in grid.items():
        t = tiles.get(tid)
        if not t:
            continue
        rgb = t.rgb()
        ox, oy = col * 8 + fine, row * 8
        for yy in range(8):
            for xx in range(8):
                X, Y = ox + xx, oy + yy
                if 0 <= X < 256 and 0 <= Y < 240:
                    px[X, Y] = rgb[yy * 8 + xx]
    if scale != 1:
        img = img.resize((256 * scale, 240 * scale), Image.NEAREST)
    return img


HUD_TOP = 0  # set from --hud-rows; hashes/matching ignore cell rows below it


def grid_hash(grid):
    return hash(tuple(sorted((k, v) for k, v in grid.items() if k[1] >= HUD_TOP)))


def stable_screens(frames, tiles, min_stable, hud_rows):
    """Collapse consecutive identical frames; returns list of dicts."""
    screens = []
    prev_h, run, first = None, 0, None
    seq = []  # per frame: (hash, grid, fine)
    for fno, rows in frames:
        fine, grid = frame_grid(rows, tiles)
        seq.append((fno, fine, grid))
    i = 0
    while i < len(seq):
        h = grid_hash(seq[i][2])
        j = i
        while j + 1 < len(seq) and grid_hash(seq[j + 1][2]) == h:
            j += 1
        if j - i + 1 >= min_stable and len(seq[i][2]) >= 32 * 30 // 2:
            screens.append({"first": i, "last": j, "hash": h, "fine": seq[i][1], "grid": seq[i][2]})
        i = j + 1
    return seq, screens


def shift_match(a, b, hud_rows):
    """Best (dx, dy) in cells such that b(col,row) == a(col+dx,row+dy) for the
    playfield; returns (dx, dy, score)."""
    best = (0, 0, -1)
    for dy in range(-22, 23):
        for dx in range(-31, 32):
            if dx == 0 and dy == 0:
                continue
            hit = tot = 0
            for (c, r), tid in b.items():
                if r < hud_rows:
                    continue
                tot += 1
                if a.get((c + dx, r + dy)) == tid:
                    hit += 1
            if tot and hit / tot > best[2]:
                best = (dx, dy, hit / tot)
    return best


def stitch(seq, screens, tiles, hud_rows, out):
    """Place each stable screen relative to the previous one using the scroll
    observed in a mid-transition frame."""
    if not screens:
        return None
    pos = {screens[0]["hash"]: (0, 0)}
    placed = {screens[0]["hash"]: screens[0]}
    log = []
    anchor = screens[0]
    for k in range(1, len(screens)):
        a, b = anchor, screens[k]
        if b["hash"] in pos:
            anchor = b  # back on a known screen: re-anchor there
            continue
        if screens[k - 1]["hash"] != a["hash"]:
            # an unplaced screen sits between anchor and b (cut/cave): no link
            log.append(f"screen {k}: not adjacent to the anchor, skipped")
            continue
        a = screens[k - 1]
        # a mid-transition frame: halfway between a.last and b.first
        # early-transition frame: mostly A, shifted a few cells (a mid frame is
        # half A / half B and matches neither above 0.5)
        mid = a["last"] + max(2, (b["first"] - a["last"]) // 4)
        if mid <= a["last"] or mid >= b["first"]:
            log.append(f"screen {k}: no transition frame (cut), skipped")
            continue
        mid_grid = seq[mid][2]
        dx, dy, s = shift_match(a["grid"], mid_grid, hud_rows)
        if s < 0.5:
            log.append(f"screen {k}: transition match {s:.2f} too low, skipped")
            continue
        # content moved by (dx,dy) cells from a to mid: camera moved by (+dx,+dy)
        # -> screen b sits one screen further in that direction
        sx = (1 if dx > 0 else -1 if dx < 0 else 0)
        sy = (1 if dy > 0 else -1 if dy < 0 else 0)
        if sx and sy:
            sy = 0 if abs(dx) >= abs(dy) else sy
            sx = 0 if sy else sx
        ax, ay = pos[a["hash"]]
        pos[b["hash"]] = (ax + sx, ay + sy)
        placed[b["hash"]] = b
        anchor = b
        log.append(f"screen {k}: shift ({dx},{dy}) match {s:.2f} -> placed at ({ax + sx},{ay + sy})")
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    W, H = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    play_h = 240 - hud_rows * 8
    canvas = Image.new("RGB", (W * 256, H * play_h), (20, 20, 20))
    for h, (x, y) in pos.items():
        scr = render_grid(placed[h]["grid"], tiles, placed[h]["fine"])
        canvas.paste(scr.crop((0, hud_rows * 8, 256, 240)), ((x - min(xs)) * 256, (y - min(ys)) * play_h))
    canvas.save(os.path.join(out, "stitched.png"))
    return log, len(pos)


def shift_match_x(a, b, hud_rows, max_dx):
    best = (0, -1.0)
    for dx in range(-max_dx, max_dx + 1):
        hit = tot = 0
        for (c, r), tid in b.items():
            if r < hud_rows:
                continue
            tot += 1
            if a.get((c + dx, r)) == tid:
                hit += 1
        if tot and hit / tot > best[1]:
            best = (dx, hit / tot)
    return best


def stitch_continuous(seq, tiles, hud_rows, out, step, max_dx):
    """Horizontal scroller: accumulate the per-frame camera shift (in cells)
    and paint every sampled frame's aligned grid at its world position."""
    world = {}  # (world_col, row) -> tid
    cum = 0
    prev = None
    log = []
    for i in range(0, len(seq), step):
        fno, fine, grid = seq[i]
        if len(grid) < 200:
            continue
        if prev is not None:
            dx, score = shift_match_x(prev, grid, hud_rows, max_dx)
            if score < 0.5:
                log.append(f"frame {fno}: match {score:.2f} < 0.5, cut -> new segment")
                cum += 40  # gap
            else:
                cum += dx
        for (c, r), tid in grid.items():
            if r >= hud_rows:
                world.setdefault((c + cum, r), tid)
        prev = grid
    cols = [c for c, r in world]
    c0, c1 = min(cols), max(cols)
    W = (c1 - c0 + 1) * 8
    H = (30 - hud_rows) * 8
    img = Image.new("RGB", (W, H), (20, 20, 20))
    px = img.load()
    for (c, r), tid in world.items():
        rgb = tiles[tid].rgb()
        ox, oy = (c - c0) * 8, (r - hud_rows) * 8
        for yy in range(8):
            for xx in range(8):
                px[ox + xx, oy + yy] = rgb[yy * 8 + xx]
    img.save(os.path.join(out, "stitched.png"))
    return log, W


def metatiles(seq, tiles, hud_rows, mt_x0, mt_y0):
    """Vocabulary of 2x2 shape tuples aligned to (mt_x0, mt_y0) cell parity,
    plus E/S adjacency counts between metatiles. `seq` should hold aligned
    frames only (stable screens for a screen-based game): a frame caught
    mid-vertical-scroll breaks the row parity."""
    vocab = collections.Counter()
    art = {}  # metatile -> representative tile ids (for rendering)
    east = collections.Counter()
    south = collections.Counter()
    seen_frames = set()
    for fno, fine, grid in seq:
        h = grid_hash(grid)
        if h in seen_frames:
            continue  # count each distinct screen once, not per frame
        seen_frames.add(h)
        mts = {}
        cols = sorted({c for c, r in grid})
        rows = sorted({r for c, r in grid})
        for r in range(hud_rows, 30, 1):
            if (r - mt_y0) % 2:
                continue
            for c in range(-1, 32):
                if (c - mt_x0) % 2:
                    continue
                ids = [grid.get((c, r)), grid.get((c + 1, r)), grid.get((c, r + 1)), grid.get((c + 1, r + 1))]
                if any(i is None for i in ids):
                    continue
                key = tuple(tiles[i].shape for i in ids)
                vocab[key] += 1
                art.setdefault(key, ids)
                mts[(c, r)] = key
        for (c, r), k in mts.items():
            e = mts.get((c + 2, r))
            if e is not None:
                east[(k, e)] += 1
            s = mts.get((c, r + 2))
            if s is not None:
                south[(k, s)] += 1
    return vocab, art, east, south


def render_metatile(key, art, tiles, scale=2):
    ids = art[key]
    img = Image.new("RGB", (16, 16))
    px = img.load()
    for n, tid in enumerate(ids):
        rgb = tiles[tid].rgb()
        ox, oy = (n % 2) * 8, (n // 2) * 8
        for yy in range(8):
            for xx in range(8):
                px[ox + xx, oy + yy] = rgb[yy * 8 + xx]
    return img.resize((16 * scale, 16 * scale), Image.NEAREST)


def contact_sheet(items, render, per_row, cell, gutter, out_path, labels=None):
    n = len(items)
    rows = (n + per_row - 1) // per_row
    W = per_row * (cell + gutter) + gutter
    H = rows * (cell + gutter + 10) + gutter
    sheet = Image.new("RGB", (W, H), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    for i, it in enumerate(items):
        x = gutter + (i % per_row) * (cell + gutter)
        y = gutter + (i // per_row) * (cell + gutter + 10)
        sheet.paste(render(it), (x, y))
        if labels:
            d.text((x, y + cell), labels[i], fill=(200, 200, 200))
    sheet.save(out_path)


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[a] = b


def group(vocab, east, south, min_count, min_prob):
    """Mutual-predictability grouping. Returns components (lists of keys)."""
    out_e = collections.Counter()
    in_e = collections.Counter()
    out_s = collections.Counter()
    in_s = collections.Counter()
    for (a, b), n in east.items():
        out_e[a] += n
        in_e[b] += n
    for (a, b), n in south.items():
        out_s[a] += n
        in_s[b] += n
    dsu = DSU()
    edges = []
    for (a, b), n in east.items():
        if a == b or n < min_count:
            continue
        p_ab = n / out_e[a]
        p_ba = n / in_e[b]
        if p_ab >= min_prob and p_ba >= min_prob:
            dsu.union(a, b)
            edges.append((a, b, "E", n, p_ab, p_ba))
    for (a, b), n in south.items():
        if a == b or n < min_count:
            continue
        p_ab = n / out_s[a]
        p_ba = n / in_s[b]
        if p_ab >= min_prob and p_ba >= min_prob:
            dsu.union(a, b)
            edges.append((a, b, "S", n, p_ab, p_ba))
    comps = collections.defaultdict(list)
    for k in vocab:
        comps[dsu.find(k)].append(k)
    return [c for c in comps.values() if len(c) > 1], edges


def baseline_tiles(seq, tiles, hud_rows):
    """F5.4e criterion: tile shapes adjacent (E/S) >= 2 times, union-find."""
    co = collections.Counter()
    seen = set()
    for fno, fine, grid in seq:
        h = grid_hash(grid)
        if h in seen:
            continue
        seen.add(h)
        for (c, r), tid in grid.items():
            if r < hud_rows:
                continue
            a = tiles[tid].shape
            for nb in ((c + 1, r), (c, r + 1)):
                t2 = grid.get(nb)
                if t2 is not None:
                    b = tiles[t2].shape
                    co[(min(a, b), max(a, b))] += 1
    dsu = DSU()
    for (a, b), n in co.items():
        if n >= 2 and a != b:
            dsu.union(a, b)
    comps = collections.Counter()
    for k in set(x for pair in co for x in pair):
        comps[dsu.find(k)] += 1
    return sorted(comps.values(), reverse=True)


def layout_object(comp, edges, art, tiles, path):
    """BFS placement of a component's metatiles at their E/S offsets."""
    adj = collections.defaultdict(list)
    keyset = set(comp)
    for a, b, d, n, pa, pb in edges:
        if a in keyset and b in keyset:
            off = (1, 0) if d == "E" else (0, 1)
            adj[a].append((b, off))
            adj[b].append((a, (-off[0], -off[1])))
    start = max(comp, key=lambda k: len(adj[k]))
    pos = {start: (0, 0)}
    q = [start]
    while q:
        k = q.pop(0)
        for nb, (dx, dy) in adj[k]:
            if nb not in pos:
                pos[nb] = (pos[k][0] + dx, pos[k][1] + dy)
                q.append(nb)
    for k in comp:
        if k not in pos:
            pos[k] = (max(p[0] for p in pos.values()) + 1, 0)
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    W, H = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    img = Image.new("RGB", (W * 32, H * 32), (255, 0, 255))
    for k, (x, y) in pos.items():
        img.paste(render_metatile(k, art, tiles, 2), ((x - min(xs)) * 32, (y - min(ys)) * 32))
    img.save(path)
    return W, H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--out", required=True)
    ap.add_argument("--hud-rows", type=int, default=0, help="top cell rows to ignore (fixed HUD)")
    ap.add_argument("--mt-x0", type=int, default=0, help="metatile column parity origin (cells)")
    ap.add_argument("--mt-y0", type=int, default=0, help="metatile row parity origin (cells)")
    ap.add_argument("--min-stable", type=int, default=15)
    ap.add_argument("--min-count", type=int, default=3)
    ap.add_argument("--min-prob", type=float, default=0.6)
    ap.add_argument("--frames-every", type=int, default=60)
    ap.add_argument("--hud-rows-bottom", type=int, default=0)
    ap.add_argument("--continuous", action="store_true", help="horizontal scroller: stitch by per-frame shift")
    ap.add_argument("--step", type=int, default=3, help="frame sampling step for --continuous")
    ap.add_argument("--skip-frames", type=int, default=0, help="drop the first N frames (menus, title)")
    a = ap.parse_args()
    global HUD_BOTTOM, HUD_TOP
    HUD_BOTTOM = a.hud_rows_bottom
    HUD_TOP = a.hud_rows
    os.makedirs(os.path.join(a.out, "frames"), exist_ok=True)
    os.makedirs(os.path.join(a.out, "objects"), exist_ok=True)

    tiles, frames = parse_dump(a.dump)
    frames = frames[a.skip_frames:]
    seq, screens = stable_screens(frames, tiles, a.min_stable, a.hud_rows)
    rep = [f"frames: {len(frames)}  tiles(exact): {len(tiles)}  shapes: {len({t.shape for t in tiles.values()})}",
           f"stable screens: {len(screens)}  distinct: {len({s['hash'] for s in screens})}"]

    for i, (fno, fine, grid) in enumerate(seq):
        if i % a.frames_every == 0:
            render_grid(grid, tiles, fine).save(os.path.join(a.out, "frames", f"f{fno:05d}.png"))

    if not a.continuous and len(screens) >= 3:
        vocab_seq = [(s["first"], s["fine"], s["grid"]) for s in screens]
        rep.append("vocabulary source: stable screens")
    else:
        vocab_seq = seq
        rep.append("vocabulary source: all frames")
    vocab, art, east, south = metatiles(vocab_seq, tiles, a.hud_rows, a.mt_x0, a.mt_y0)
    rep.append(f"metatiles (2x2 shape tuples, aligned): {len(vocab)}")
    items = [k for k, _ in vocab.most_common()]
    contact_sheet(items, lambda k: render_metatile(k, art, tiles, 2), 16, 32, 6,
                  os.path.join(a.out, "metatiles.png"), [str(vocab[k]) for k in items])

    base = baseline_tiles(vocab_seq, tiles, a.hud_rows)
    comps, edges = group(vocab, east, south, a.min_count, a.min_prob)
    comps.sort(key=len, reverse=True)
    with open(os.path.join(a.out, "baseline_vs_pmi.txt"), "w") as f:
        f.write("F5.4e baseline (tile shapes, adjacency count >= 2): component sizes\n")
        f.write(f"  components: {len(base)}  largest: {base[:10]}\n")
        f.write(f"  shapes in giant component: {base[0] if base else 0} of {sum(base)}\n\n")
        f.write(f"metatile + mutual predictability (count>={a.min_count}, p>={a.min_prob}):\n")
        f.write(f"  components: {len(comps)}  sizes: {[len(c) for c in comps]}\n")
        f.write(f"  edges kept: {len(edges)} of {len(east) + len(south)}\n")
    rep.append(f"baseline giant component: {base[0] if base else 0}/{sum(base)} shapes, {len(base)} comps")
    rep.append(f"PMI objects: {len(comps)}  sizes {[len(c) for c in comps][:20]}")
    for i, c in enumerate(comps):
        W, H = layout_object(c, edges, art, tiles, os.path.join(a.out, "objects", f"obj{i:03d}.png"))
        rep.append(f"  obj{i:03d}: {len(c)} metatiles, layout {W}x{H}")

    if a.continuous:
        log, W = stitch_continuous(seq, tiles, a.hud_rows, a.out, a.step, 12)
        rep.append(f"continuous stitch: {W} px wide, {len(log)} cuts")
        rep.extend("  " + l for l in log[:20])
    else:
        st = stitch(seq, screens, tiles, a.hud_rows, a.out)
        if st:
            log, n = st
            rep.append(f"stitched screens: {n}")
            rep.extend("  " + l for l in log)
    with open(os.path.join(a.out, "report.txt"), "w") as f:
        f.write("\n".join(rep) + "\n")
    print("\n".join(rep))


if __name__ == "__main__":
    main()
