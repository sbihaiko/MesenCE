#!/usr/bin/env python3
"""Screen-side measurements for scripts/gameplay_probe.py (F9.13, clauses C/D).

Split out of the probe when it hit the 200-line guardrail. The seam is real,
not arbitrary: everything here reads *pixels* out of the captured screens,
while the probe itself reads sidecars and turns numbers into a verdict.

`backgrounds/*.orig.png` are nearest-neighbour Nx replications of the native
256x240 frame, so sampling every Nth pixel recovers that frame exactly - which
is what makes a stdlib-only implementation fast enough (91 packs in 5.9 s).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mep_build  # noqa: E402  - the tree's single PNG decoder (_png_pixels)

CELL, COLS, ROWS = 8, 32, 30
# Sampled, not read whole: 24 evenly spaced screens are plenty, and cheap.
MAX_SCREENS_SAMPLED = 24
# A near-blank screen (a fade, a wipe) proves nothing about tile reuse, so the
# D measurement abstains below this many drawn tiles rather than voting.
MIN_DRAWN_TILES = 96
# Churn needs a series to mean anything; below this many screens it abstains.
MIN_SCREENS_FOR_CHURN = 5


def _screen_tiles(path):
    """The 960 native 8x8 tiles of one captured screen, as RGB byte strings.

    The captured screens are written at the pack's scale with nearest-neighbour
    replication, so sampling every Nth pixel recovers the native frame exactly.
    """
    bmp = mep_build._png_pixels(Path(path))
    if bmp is None:
        return None
    width, height = COLS * CELL, ROWS * CELL
    if bmp.width % width or bmp.height % height:
        return None
    step_x, step_y = bmp.width // width, bmp.height // height
    stride, chans = bmp.width * bmp.channels, bmp.channels
    rows = []
    for y in range(height):
        src = bmp.raw[y * step_y * stride:y * step_y * stride + stride]
        row = bytearray(width * 3)
        row[0::3] = src[0::chans * step_x]
        row[1::3] = src[1::chans * step_x]
        row[2::3] = src[2::chans * step_x]
        rows.append(bytes(row))
    return [b"".join(rows[ty * CELL + k][tx * CELL * 3:(tx + 1) * CELL * 3] for k in range(CELL))
            for ty in range(ROWS) for tx in range(COLS)]


def screen_metrics(screen_dir):
    """`everChanged` and `reuse` over the captured screens; None each when there
    is not enough material to compute them."""
    out = {"screens": 0, "everChanged": None, "reuse": None}
    try:
        names = sorted(n for n in os.listdir(screen_dir)
                       if n.startswith("screen") and n.endswith(".orig.png"))
    except OSError:
        return out
    out["screens"] = len(names)
    if len(names) > MAX_SCREENS_SAMPLED:
        last = len(names) - 1
        picks = sorted({round(i * last / (MAX_SCREENS_SAMPLED - 1)) for i in range(MAX_SCREENS_SAMPLED)})
        names = [names[i] for i in picks]
    frames = [t for t in (_screen_tiles(os.path.join(screen_dir, n)) for n in names) if t]
    if not frames:
        return out
    best = None
    for frame in frames:
        drawn = [t for t in frame if t != t[:3] * (CELL * CELL)]
        if len(drawn) < MIN_DRAWN_TILES:
            continue
        ratio = len(drawn) / len(set(drawn))
        best = ratio if best is None else max(best, ratio)
    out["reuse"] = best
    if out["screens"] >= MIN_SCREENS_FOR_CHURN and len(frames) > 1:
        base = frames[0]
        changed = [False] * len(base)
        for frame in frames[1:]:
            for i, tile in enumerate(frame):
                if tile != base[i]:
                    changed[i] = True
        out["everChanged"] = sum(changed) / len(changed)
    return out
