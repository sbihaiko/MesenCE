#!/usr/bin/env python3
"""Spike (issue #164): how often do a captured screen's three `tileAtPosition`
anchors land on a cell that a *variant* of the same screen changes?

ADR-0050 gates every `backgrounds/screenNNN.png` on three `tileAtPosition`
conditions, picked as the rarest non-flat tiles on the frame, >= 64 px apart.
Rarity is the property that makes a false match on some *other* screen
unlikely - and it is also, on most games, the property of a score digit, a
timer, a blinking prompt. When one of those three tiles changes, the whole
`<background>` stops drawing, and since ADR-0156 the cells routed off
`metatiles.png` onto that screen then render vanilla.

This spike sizes the exposure from the packs already on disk, with no
recording. Method, per pack:

  1. downsample every `backgrounds/screenNNN.orig.png` back to 256x240 (it is
     a nearest-neighbour upscale by the pack scale, so this is exact);
  2. call two screens *variants* of each other when they agree on at least
     `--variant-threshold` of their 960 8x8 blocks - i.e. they are the same
     screen with something changed on it;
  3. read the real anchors back out of `hires.txt` and check, for every
     ordered variant pair (i, j), whether all three of screen i's anchor
     blocks survive unchanged on screen j. If any changed, screen i's
     `<background>` does not draw there;
  4. re-pick anchors under the proposed rule - same rarity ranking, same
     spread, but only over blocks that no variant of that screen changes -
     and repeat both measurements.

Two rates matter and they pull against each other:

  * **miss** - variant pairs where the screen's own condition fails. The
    defect in issue #164.
  * **cross** - pairs of screens that are *not* variants where screen i's
    condition still matches. A false match draws the wrong screen. This is
    what the rarity-first rule was buying, so a fix that trades misses for
    cross-matches is not a fix.

**This is an approximation of the shipped rule, not the rule.** It can only
see the screens that were captured; a variant the recording never held still
on is invisible here, and those are exactly the ones that bite in the wild.
It also compares *pixels* where the condition compares tile index + palette,
so two distinct tile indices that render identically read as "unchanged" here
and would fail in the emulator - so the miss numbers below are a lower bound.

Usage:
  scripts/spike_anchor_stability.py <pack-or-library> [--json]
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

try:
    from PIL import Image
except ImportError:
    sys.exit("this spike needs Pillow (already used by scripts/mep_build.py)")

SCREEN_W = 256
SCREEN_H = 240
COLS = SCREEN_W // 8
ROWS = SCREEN_H // 8
SPREAD = 64  # ADR-0050: anchors at least 64 px apart (Manhattan)

COND_RE = re.compile(r"^<condition>([^,]+),tileAtPosition,(-?\d+),(-?\d+),")
BG_RE = re.compile(r"^\[([^\]]+)\]<background>backgrounds/(screen\d+)\.png")


def load_screens(textures_dir):
    """screen name -> list of 960 block fingerprints (row-major, 8x8 RGBA)."""
    bg_dir = os.path.join(textures_dir, "backgrounds")
    if not os.path.isdir(bg_dir):
        return {}
    screens = {}
    for name in sorted(os.listdir(bg_dir)):
        if not name.endswith(".orig.png"):
            continue
        base = name[: -len(".orig.png")]
        img = Image.open(os.path.join(bg_dir, name)).convert("RGBA")
        scale = img.width // SCREEN_W
        if scale < 1 or img.width % SCREEN_W:
            continue
        if scale > 1:
            img = img.resize((SCREEN_W, SCREEN_H), Image.NEAREST)
        px = img.tobytes()
        stride = SCREEN_W * 4
        blocks = []
        for row in range(ROWS):
            for col in range(COLS):
                top = row * 8
                left = col * 32
                blocks.append(b"".join(
                    px[(top + i) * stride + left:(top + i) * stride + left + 32]
                    for i in range(8)
                ))
        screens[base] = blocks
    return screens


def parse_anchors(textures_dir):
    """screen name -> list of (row, col) block indices of its anchors."""
    path = os.path.join(textures_dir, "hires.txt")
    if not os.path.isfile(path):
        return {}
    conds = {}
    backgrounds = {}
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            m = COND_RE.match(line)
            if m:
                conds[m.group(1)] = (int(m.group(2)), int(m.group(3)))
                continue
            m = BG_RE.match(line)
            if m:
                backgrounds[m.group(2)] = [n.strip() for n in m.group(1).split("&")]
    out = {}
    for screen, names in backgrounds.items():
        cells = []
        for name in names:
            if name not in conds:
                continue
            x, y = conds[name]
            if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
                cells.append((y // 8, x // 8))
        out[screen] = cells
    return out


def is_flat(block):
    first = block[0:4]
    return all(block[i:i + 4] == first for i in range(0, len(block), 4))


def pick_anchors(blocks, allowed, rarity):
    """The ADR-0050 greedy, over `allowed` block indices only."""
    ranked = sorted(
        (i for i in allowed if not is_flat(blocks[i])),
        key=lambda i: (rarity[blocks[i]], i),
    )
    picked = []
    for idx in ranked:
        row, col = divmod(idx, COLS)
        x, y = col * 8, row * 8
        if all(abs(x - px) + abs(y - py) >= SPREAD for px, py in picked):
            picked.append((x, y))
        if len(picked) == 3:
            break
    return [(y // 8, x // 8) for x, y in picked]


def pick_anchors_guarded(name, names, screens, variants, rarity, allowed, topk=40):
    """Stable-first, but driven by discrimination: at every step take the
    candidate that leaves the fewest *non-variant* screens still matching."""
    blocks = screens[name]
    ranked = sorted(
        (i for i in allowed if not is_flat(blocks[i])),
        key=lambda i: (rarity[blocks[i]], i),
    )[:topk]
    others = [o for o in names if o != name and o not in variants[name]]
    alive = list(others)
    picked = []
    while len(picked) < 3 and ranked:
        best = None
        for idx in ranked:
            row, col = divmod(idx, COLS)
            x, y = col * 8, row * 8
            if any(abs(x - px) + abs(y - py) < SPREAD for px, py in picked):
                continue
            still = sum(1 for o in alive if screens[o][idx] == blocks[idx])
            key = (still, rarity[blocks[idx]], idx)
            if best is None or key < best[0]:
                best = (key, idx)
        if best is None:
            break
        idx = best[1]
        row, col = divmod(idx, COLS)
        picked.append((col * 8, row * 8))
        alive = [o for o in alive if screens[o][idx] == blocks[idx]]
        ranked = [i for i in ranked if i != idx]
    return [(y // 8, x // 8) for x, y in picked], len(alive) if picked else len(others)


def analyse(textures_dir, threshold):
    screens = load_screens(textures_dir)
    anchors = parse_anchors(textures_dir)
    names = [n for n in sorted(screens) if n in anchors and anchors[n]]
    if not names:
        return None

    rarity = defaultdict(int)
    for name in names:
        for block in screens[name]:
            rarity[block] += 1

    # variant relation
    variants = {n: set() for n in names}
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            ba, bb = screens[names[a]], screens[names[b]]
            same = sum(1 for i in range(len(ba)) if ba[i] == bb[i])
            if same >= threshold * len(ba):
                variants[names[a]].add(names[b])
                variants[names[b]].add(names[a])

    def holds(anchor_cells, target):
        source = screens[target[0]]
        other = screens[target[1]]
        return all(source[r * COLS + c] == other[r * COLS + c] for r, c in anchor_cells)

    stats = {
        "pack": os.path.basename(os.path.dirname(os.path.dirname(textures_dir.rstrip("/")))),
        "screens": len(names),
        "variant_pairs": 0,
        "miss_before": 0,
        "miss_after": 0,
        "cross_pairs": 0,
        "cross_before": 0,
        "cross_after": 0,
        "anchors_before": 0,
        "anchors_before_unstable": 0,
        "screens_with_unstable_anchor": 0,
        "screens_short_after": 0,
        "screens_no_anchor_after": 0,
    }

    # proposed rule: only blocks no variant of this screen changes
    new_anchors = {}
    for name in names:
        blocks = screens[name]
        stable = []
        for i in range(len(blocks)):
            if all(screens[v][i] == blocks[i] for v in variants[name]):
                stable.append(i)
        picked, cross_stable = pick_anchors_guarded(
            name, names, screens, variants, rarity, stable)
        if len(picked) < 3 or cross_stable:
            # the stable region cannot tell this screen from another one; keep
            # the wider candidate set rather than draw the wrong screen
            wide, cross_wide = pick_anchors_guarded(
                name, names, screens, variants, rarity, range(len(blocks)))
            if len(wide) > len(picked) or cross_wide < cross_stable:
                picked = wide
        if len(picked) < 3:
            # fall back to the whole frame rather than ship fewer conditions
            extra = pick_anchors(blocks, range(len(blocks)), rarity)
            for cell in extra:
                if cell not in picked and len(picked) < 3:
                    picked.append(cell)
            stats["screens_short_after"] += 1
        if not picked:
            stats["screens_no_anchor_after"] += 1
        new_anchors[name] = picked

    for name in names:
        old = anchors[name]
        stats["anchors_before"] += len(old)
        blocks = screens[name]
        bad = [c for c in old if any(screens[v][c[0] * COLS + c[1]] != blocks[c[0] * COLS + c[1]]
                                     for v in variants[name])]
        stats["anchors_before_unstable"] += len(bad)
        if bad:
            stats["screens_with_unstable_anchor"] += 1
        for other in names:
            if other == name:
                continue
            if other in variants[name]:
                stats["variant_pairs"] += 1
                if not holds(old, (name, other)):
                    stats["miss_before"] += 1
                if not holds(new_anchors[name], (name, other)):
                    stats["miss_after"] += 1
            else:
                stats["cross_pairs"] += 1
                if holds(old, (name, other)):
                    stats["cross_before"] += 1
                if new_anchors[name] and holds(new_anchors[name], (name, other)):
                    stats["cross_after"] += 1
    return stats


def find_texture_dirs(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        if "hires.txt" in filenames and os.path.isdir(os.path.join(dirpath, "backgrounds")):
            out.append(dirpath)
            dirnames[:] = []
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--variant-threshold", type=float, default=0.90)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    dirs = find_texture_dirs(args.root)
    rows = []
    for d in dirs:
        stats = analyse(d, args.variant_threshold)
        if stats:
            rows.append(stats)

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    total = defaultdict(int)
    print(f"variant threshold {args.variant_threshold:.2f}")
    hdr = (f"{'pack':38} {'scr':>4} {'anc':>5} {'unstable':>9} "
           f"{'vpairs':>7} {'miss>':>6} {'miss<':>6} {'xpairs':>7} {'x>':>5} {'x<':>5}")
    print(hdr)
    for r in rows:
        for k, v in r.items():
            if isinstance(v, int):
                total[k] += v
        print(f"{r['pack'][:38]:38} {r['screens']:4} {r['anchors_before']:5} "
              f"{r['anchors_before_unstable']:9} {r['variant_pairs']:7} "
              f"{r['miss_before']:6} {r['miss_after']:6} {r['cross_pairs']:7} "
              f"{r['cross_before']:5} {r['cross_after']:5}")
    print("-" * len(hdr))
    print(f"{'TOTAL':38} {total['screens']:4} {total['anchors_before']:5} "
          f"{total['anchors_before_unstable']:9} {total['variant_pairs']:7} "
          f"{total['miss_before']:6} {total['miss_after']:6} {total['cross_pairs']:7} "
          f"{total['cross_before']:5} {total['cross_after']:5}")
    if total["anchors_before"]:
        print(f"unstable anchors: {total['anchors_before_unstable']}/{total['anchors_before']} "
              f"({100.0 * total['anchors_before_unstable'] / total['anchors_before']:.1f}%)")
    if total["variant_pairs"]:
        print(f"variant pairs missed: before {total['miss_before']}/{total['variant_pairs']} "
              f"({100.0 * total['miss_before'] / total['variant_pairs']:.1f}%), "
              f"after {total['miss_after']}/{total['variant_pairs']} "
              f"({100.0 * total['miss_after'] / total['variant_pairs']:.1f}%)")
    if total["cross_pairs"]:
        print(f"non-variant false matches: before {total['cross_before']}/{total['cross_pairs']}, "
              f"after {total['cross_after']}/{total['cross_pairs']}")
    print(f"screens with >=1 unstable anchor: {total['screens_with_unstable_anchor']}/{total['screens']}")
    print(f"screens with <3 stable candidates: {total['screens_short_after']}/{total['screens']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
