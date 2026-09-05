#!/usr/bin/env python3
"""Inventory + noise budget for the artist-legible sheets of ADR-0153 (Phase 9).

This is the automatable half of the PRD Phase 9 validation panel: it reports
what a pack's `textures/sheets/` actually contains (grid unit and how it was
decided, cells per context, object and map sizes) and computes validation
test 7, the noise budget - `misc` cells must stay under 15 % of scene cells.
The judgement calls (cold read, side-by-side with the artist pack, map
recognisability) stay human; this only tells a person where to look.

Usage:
  scripts/sheet_report.py <pack-or-library> [--json] [--fail-noise]

<pack-or-library> may be a pack folder (containing sheets/ or textures/sheets/)
or a ROM library, in which case every <Game>/auto/textures/sheets is reported.
"""
import argparse
import json
import os
import sys

NOISE_BUDGET = 0.15  # ADR-0153 / PRD Phase 9 validation test 7


def find_sheet_dirs(root):
    """Yield every sheets/ folder under `root`, or `root` itself when it is one."""
    for candidate in (root, os.path.join(root, "sheets"), os.path.join(root, "textures", "sheets")):
        if os.path.isdir(candidate) and any(f.endswith(".json") for f in os.listdir(candidate)):
            return [candidate]
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        if os.path.basename(dirpath) == "sheets" and any(f.endswith(".json") for f in filenames):
            found.append(dirpath)
            dirnames[:] = []
    return sorted(found)


def load_sheets(sheet_dir):
    sheets = {}
    for name in sorted(os.listdir(sheet_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(sheet_dir, name)
        try:
            with open(path) as handle:
                doc = json.load(handle)
        except (OSError, ValueError) as err:
            sheets[name] = {"error": str(err)}
            continue
        if doc.get("version") != 1:
            sheets[name] = {"error": "unsupported version %r" % doc.get("version")}
            continue
        sheets[name] = doc
    return sheets


def summarize(sheet_dir):
    sheets = load_sheets(sheet_dir)
    scene = sum(len(d.get("cells", [])) for n, d in sheets.items()
                if "error" not in d and d.get("kind") == "metatiles")
    misc = sum(len(d.get("cells", [])) for n, d in sheets.items()
               if "error" not in d and d.get("kind") == "misc")
    grid = next((d for d in sheets.values() if "error" not in d and d.get("kind") == "metatiles"), None)
    objects = [d for n, d in sheets.items() if "error" not in d and d.get("kind") in ("object", "sprite")]
    maps = [d for n, d in sheets.items() if "error" not in d and d.get("kind") == "map"]

    denominator = scene + misc
    return {
        "path": sheet_dir,
        "errors": {n: d["error"] for n, d in sheets.items() if "error" in d},
        "gridUnit": grid.get("gridUnit") if grid else None,
        "gridConsistency": grid.get("gridConsistency") if grid else None,
        "gridPhase": grid.get("gridPhase") if grid else None,
        "cells": {kind: sum(len(d.get("cells", [])) for n, d in sheets.items()
                            if "error" not in d and d.get("kind") == kind)
                  for kind in ("metatiles", "hud", "font", "misc")},
        "objects": sorted((len(d.get("cells", [])) for d in objects), reverse=True),
        "maps": [{"mode": d.get("mode"), "placements": len(d.get("placements", []))} for d in maps],
        "noise": (misc / denominator) if denominator else 0.0,
        "noiseOk": (misc / denominator if denominator else 0.0) < NOISE_BUDGET,
    }


def print_summary(summary):
    name = os.path.relpath(summary["path"])
    print("== %s" % name)
    if summary["errors"]:
        for sheet, err in summary["errors"].items():
            print("   ERROR %s: %s" % (sheet, err))
    if summary["gridUnit"] is None:
        print("   no metatiles.json - nothing to read")
        return
    consistency = summary["gridConsistency"] or {}
    print("   grid      : %spx phase (%s,%s)  consistency %.2f vs 8x8 %.2f" % (
        summary["gridUnit"],
        (summary["gridPhase"] or {}).get("x"), (summary["gridPhase"] or {}).get("y"),
        consistency.get("chosen", 0.0), consistency.get("alt8x8", 0.0)))
    cells = summary["cells"]
    print("   cells     : scene %d  hud %d  font %d  misc %d" % (
        cells["metatiles"], cells["hud"], cells["font"], cells["misc"]))
    print("   noise     : %.1f%% %s (budget %.0f%%)" % (
        summary["noise"] * 100, "OK" if summary["noiseOk"] else "OVER", NOISE_BUDGET * 100))
    objects = summary["objects"]
    print("   objects   : %d%s" % (len(objects), (" (largest %s)" % objects[:5]) if objects else ""))
    for entry in summary["maps"]:
        print("   map       : %s, %d placements" % (entry["mode"], entry["placements"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--fail-noise", action="store_true", help="exit 1 when any pack blows the noise budget")
    args = parser.parse_args()

    dirs = find_sheet_dirs(args.target)
    if not dirs:
        print("no sheets/ folder with sidecar JSON under %s" % args.target, file=sys.stderr)
        return 1

    summaries = [summarize(d) for d in dirs]
    if args.json:
        json.dump(summaries, sys.stdout, indent=2)
        print()
    else:
        for summary in summaries:
            print_summary(summary)

    if args.fail_noise and any(not s["noiseOk"] for s in summaries if s["gridUnit"] is not None):
        print("noise budget exceeded (PRD Phase 9 validation test 7)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
