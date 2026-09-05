#!/usr/bin/env python3
"""Spike: how much of a sheet is the *same subject* arriving under several keys.

The repaint budget an artist actually faces is measured in **subjects**, not in
vocabulary cells. Two things inflate the cell count without adding a subject:

- **Bank duplication.** A mapper that swaps CHR banks per animation frame
  (MMC2 in Punch-Out!!, MMC3 elsewhere) delivers the same drawing under a
  different tile key, so the vocabulary holds it twice, pixel for pixel.
- **Animation neighbours.** Consecutive frames of one figure differ in a few
  pixels; each still costs its own hand-painted cell today.

This measures both: exact-duplicate collapse and near-duplicate collapse at a
tolerance, per pack. It decides nothing on its own - it sizes the prize before
ADR-0153's vocabulary gains an alias pass.

Usage:
  scripts/spike_sheet_dedup.py <pack-or-library> [--tolerance 0.10] [--json]
"""
import argparse
import json
import os
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("this spike needs Pillow (already used by scripts/mep_build.py)")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sheet_report import find_sheet_dirs  # noqa: E402  - same repo, same folder


def cell_crops(sheet_dir):
    """1x crops of every metatile cell, from the .orig.png twin (F5.4d)."""
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
    crops = [image.crop((c["x"], c["y"], c["x"] + unit, c["y"] + unit)).tobytes()
             for c in doc.get("cells", [])]
    return doc, crops


def collapse(crops, tolerance):
    """(exact-distinct, near-duplicate clusters) under a per-byte tolerance."""
    if not crops:
        return 0, 0
    exact = len(set(crops))
    budget = int(tolerance * len(crops[0]))
    representatives = []
    for crop in crops:
        matched = False
        for rep in representatives:
            diff = 0
            for a, b in zip(crop, rep):
                if a != b:
                    diff += 1
                    if diff > budget:
                        break
            if diff <= budget:
                matched = True
                break
        if not matched:
            representatives.append(crop)
    return exact, len(representatives)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--tolerance", type=float, default=0.10,
                        help="share of channel bytes allowed to differ (default 0.10)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = []
    for sheet_dir in find_sheet_dirs(args.target):
        doc, crops = cell_crops(sheet_dir)
        if doc is None:
            continue
        exact, clusters = collapse(crops, args.tolerance)
        cells = len(crops)
        rows.append({
            "path": sheet_dir,
            "cells": cells,
            "exactDistinct": exact,
            "clusters": clusters,
            "exactCollapse": (cells - exact) / cells if cells else 0.0,
            "nearCollapse": (cells - clusters) / cells if cells else 0.0,
        })

    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        print()
        return 0

    print("%-44s %6s %7s %8s %8s" % ("pack", "cells", "exact", "clusters", "collapse"))
    for row in sorted(rows, key=lambda r: -r["nearCollapse"]):
        name = row["path"].split(os.sep)
        name = name[name.index("roms") + 1] if "roms" in name else row["path"]
        print("%-44s %6d %7d %8d %7.0f%%" % (
            name[:44], row["cells"], row["exactDistinct"], row["clusters"],
            row["nearCollapse"] * 100))
    if rows:
        cells = sum(r["cells"] for r in rows)
        clusters = sum(r["clusters"] for r in rows)
        print("\n%d packs: %d cells collapse to %d subjects (%.0f%%)" % (
            len(rows), cells, clusters, 100 * (1 - clusters / cells)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
