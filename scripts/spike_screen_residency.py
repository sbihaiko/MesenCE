#!/usr/bin/env python3
"""Spike (F9.9): how much of `metatiles.png` is really a piece of one captured screen.

ADR-0050 already writes every static screen as `backgrounds/screenNNN.png` -
the only *positional* surface the HD Pack format has. ADR-0153 then spends the
same content a second time, as loose cells on the `metatiles.png` contact
sheet. For a cell whose whole recorded life happened inside one captured
screen, that second copy buys the artist nothing: the screen is repainted
whole, and the cell can never be painted anywhere else.

This spike sizes that overlap from the packs already on disk, with no
recording. Method, per pack:

  1. crop every `metatiles.orig.png` cell at 1x (the F5.4d pixel-exact twin);
  2. downsample every `backgrounds/screenNNN.orig.png` back to 256x240 (it is
     a nearest-neighbour upscale by the pack scale, so this is exact);
  3. slide the sheet's grid over each screen - searching the pixel offset,
     since the vocabulary is cut relative to the fine scroll and the PNG is
     not - and record every position where a cell matches, compared
     palette-agnostically (the vocabulary keys on shapes, not on colours).

It reports, per pack: cells that show up on no captured screen (they are
gameplay content and stay on the sheet whatever the rule), cells that show up
on exactly one (the routing candidates), and cells shared by several screens
(reusable vocabulary - they stay).

**This is an upper bound, not the rule.** The rule (ADR-0156) also requires
that the cell never appear at an *unexplained* position or under a different
fine scroll in a frame that was not captured, which is provenance only the
recorder has - a pack on disk cannot show it. So a scrolling game's number
here is inflated: Super Mario Bros.' ground cell sits on its captured screen
and also under every scroll offset of the level, and only the recorder can
tell the two apart.

Usage:
  scripts/spike_screen_residency.py <pack-or-library> [--json]
"""
import argparse
import json
import os
import sys
from collections import defaultdict

try:
    from PIL import Image
except ImportError:
    sys.exit("this spike needs Pillow (already used by scripts/mep_build.py)")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sheet_report import find_sheet_dirs  # noqa: E402  - same repo, same folder

SCREEN_W = 256
SCREEN_H = 240


def normalize(crop, unit):
    """Palette-agnostic fingerprint of a unit x unit RGB crop: each distinct
    colour replaced by its first-appearance rank.

    The vocabulary keys on *shapes* with the palette wildcarded
    (HdPackBuilder::ShapeIdFor), and a sheet cell is drawn with the first exact
    palette variant the recorder happened to see for that shape, which is not
    necessarily the one the captured screen was displaying. Comparing raw RGB
    therefore measures palette luck, not overlap: it scores The Legend of Zelda
    at 0 of 219 cells. Ranking the colours compares what the vocabulary itself
    considers identity."""
    order = {}
    out = bytearray(unit * unit)
    for i in range(unit * unit):
        pixel = crop[i * 3:i * 3 + 3]
        rank = order.get(pixel)
        if rank is None:
            rank = len(order)
            order[pixel] = rank
        out[i] = rank if rank < 255 else 255
    return bytes(out)


def load_metatiles(sheet_dir):
    """(doc, {cell pixels: cell index}) from the pixel-exact 1x twin."""
    doc_path = os.path.join(sheet_dir, "metatiles.json")
    if not os.path.exists(doc_path):
        return None, None
    with open(doc_path) as handle:
        doc = json.load(handle)
    reference = doc.get("reference") or "metatiles.orig.png"
    image_path = os.path.join(sheet_dir, reference)
    if not os.path.exists(image_path):
        return None, None
    image = Image.open(image_path).convert("RGB")
    unit = doc.get("gridUnit", 16)
    by_pixels = {}
    for index, cell in enumerate(doc.get("cells", [])):
        crop = image.crop((cell["x"], cell["y"], cell["x"] + unit, cell["y"] + unit)).tobytes()
        by_pixels.setdefault(normalize(crop, unit), index)
    return doc, by_pixels


def screen_paths(sheet_dir):
    """The captured screens of the pack this sheets/ folder belongs to."""
    backgrounds = os.path.join(os.path.dirname(sheet_dir), "backgrounds")
    if not os.path.isdir(backgrounds):
        return []
    return [os.path.join(backgrounds, name) for name in sorted(os.listdir(backgrounds))
            if name.endswith(".orig.png")]


def downsample(path):
    """A captured screen back at 1x. CaptureScreen writes the twin as a plain
    nearest-neighbour upscale, so dropping every scale-th pixel is exact."""
    image = Image.open(path).convert("RGB")
    scale = max(1, image.width // SCREEN_W)
    if scale == 1:
        return image
    return image.resize((image.width // scale, image.height // scale), Image.NEAREST)


def scan(image, by_pixels, unit, ox, oy, step):
    """Cell indexes found at the grid anchored on (ox, oy), every `step` cells."""
    hits = defaultdict(int)
    stride = unit * step
    for y in range(oy, image.height - unit + 1, stride):
        for x in range(ox, image.width - unit + 1, stride):
            crop = image.crop((x, y, x + unit, y + unit)).tobytes()
            index = by_pixels.get(normalize(crop, unit))
            if index is not None:
                hits[index] += 1
    return hits


def match_screen(image, by_pixels, unit):
    """Cell indexes the screen carries, with how many positions each occupies.

    The sheet's grid is expressed *relative to the frame's fine scroll*
    (HdPackBuilder::RecordGridFrame subtracts it), while the captured PNG is
    the frame as it was displayed, so the origin the vocabulary was cut at can
    land on any pixel offset within one metatile. Searching the offset is the
    difference between measuring the overlap and measuring the scroll: anchored
    on the sheet's own phase alone, Zelda scores 0 of 219 cells, which is an
    artefact and not a finding. A coarse pass picks the offset, a full pass
    counts at it."""
    best = (0, 0)
    best_score = (-1, -1)
    for oy in range(unit):
        for ox in range(unit):
            hits = scan(image, by_pixels, unit, ox, oy, 2)
            # Distinct cells first, total second. Total alone elects the
            # degenerate offset: a flat cell (one colour, e.g. Zelda's sand)
            # matches at *every* offset, so summing hits picked an alignment
            # worth 139 matches of a single cell and reported the screen as
            # carrying one cell.
            score = (len(hits), sum(hits.values()))
            if score > best_score:
                best_score = score
                best = (ox, oy)
    return scan(image, by_pixels, unit, best[0], best[1], 1)


def measure(sheet_dir):
    doc, by_pixels = load_metatiles(sheet_dir)
    if doc is None:
        return None
    cells = doc.get("cells") or []
    if not cells:
        return None
    unit = doc.get("gridUnit", 16)
    screens = screen_paths(sheet_dir)

    screens_per_cell = defaultdict(int)
    positions_per_cell = defaultdict(int)
    for path in screens:
        image = downsample(path)
        hits = match_screen(image, by_pixels, unit)
        for index, count in hits.items():
            screens_per_cell[index] += 1
            positions_per_cell[index] += count

    one = [i for i, n in screens_per_cell.items() if n == 1]
    many = [i for i, n in screens_per_cell.items() if n > 1]
    # Routing a cell retires its aliases with it - they are the same drawing.
    entries = sum(1 + len(cells[i].get("aliases") or []) for i in one)
    return {
        "path": sheet_dir,
        "screens": len(screens),
        "cells": len(cells),
        "onNoScreen": len(cells) - len(one) - len(many),
        "onOneScreen": len(one),
        "onManyScreens": len(many),
        "vocabularyEntriesMoved": entries,
        "positions": sum(positions_per_cell[i] for i in one),
        "share": len(one) / len(cells),
    }


def pack_name(path):
    parts = path.split(os.sep)
    return parts[parts.index("roms") + 1] if "roms" in parts else path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = []
    for sheet_dir in find_sheet_dirs(args.target):
        row = measure(sheet_dir)
        if row is not None:
            rows.append(row)

    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        print()
        return 0

    print("%-40s %7s %6s %7s %7s %7s %6s" % (
        "pack", "screens", "cells", "none", "one", "many", "moved"))
    for row in sorted(rows, key=lambda r: -r["share"]):
        print("%-40s %7d %6d %7d %7d %7d %5.0f%%" % (
            pack_name(row["path"])[:40], row["screens"], row["cells"],
            row["onNoScreen"], row["onOneScreen"], row["onManyScreens"],
            row["share"] * 100))
    if rows:
        cells = sum(r["cells"] for r in rows)
        one = sum(r["onOneScreen"] for r in rows)
        print("\n%d packs: %d of %d metatile cells sit on exactly one captured screen (%.0f%%)" % (
            len(rows), one, cells, 100 * one / cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
