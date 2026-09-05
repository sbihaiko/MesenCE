#!/usr/bin/env python3
"""F9.13: did a recorded pack reach gameplay, or only its menus?

`bootstrap_auto_packs.sh` used to report every recording that wrote a
`hires.txt` as `OK`, a lie of omission: a run that spent its 300 s on a password
screen writes a pack whose art is a menu. This answers the question from an
*already-written* pack on disk - no emulator, no ROM - with a reason.

The obvious proxy - pairwise pixel difference between the captured
`backgrounds/screenNNN.png` - does not work, and no clause here is one. Static
capture only fires while the screen holds still, so a game in constant motion
legitimately captures few, near-identical screens: that proxy flags Ninja Gaiden
(0.039) as hard as the Punch-Out!! password screen (0.037). "It kept showing one
screen" is equally true of a stuck menu and of a run that died at 1-1.

Calibration: over 86 packs from three recording runs of the same 30-ROM library
the four clauses flag 17 of 20 hand-labelled menu-only recordings with zero
false alarms. The three misses share one shape - a password/option screen that
is itself tiled wallpaper (Punch-Out!!, Mega Man 2, Dr. Mario). The blind spot
on the other side is a non-scrolling game with a small active area (a board
game); Tetris and Dr. Mario's playfield both clear the churn clause.

Usage: scripts/gameplay_probe.py <pack-or-library> [--json]
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Clauses C and D measure pixels in the captured screens; that half lives in
# its own module, so this file stays about the verdict.
from gameplay_screen_metrics import screen_metrics  # noqa: E402

# A: `gridConsistency.alt8x8` - how deterministically the recorded frames reuse
# the same 2x2 tile tuples. A tiled playfield saturates near 1.0 (ADR-0153 s1
# says so, which is why it no longer gates the grid unit); a run that only drew
# one-off compositions - a logo, a menu, a portrait - never accumulates repeated
# tuples. Menu-only runs 0.76-0.87, gameplay >= 0.89.
MIN_TILE_STRUCTURE = 0.86
# B: `misc` share of the vocabulary - cells that sit off the detected grid with
# no adjacency support (ADR-0153 s3); a menu is drawn at text granularity, not
# on the game's grid. Gameplay <= 0.262, stuck Gauntlet 0.635.
MAX_MISC_SHARE = 0.32
# C: screen-area churn - the share of the screen that *ever* differs from the
# first captured screen. The union of changed area, not a per-pair magnitude: a
# name/password screen rewrites a text field and nothing else, while a scrolling
# playfield moves everything even when consecutive frames look alike. Gameplay
# >= 0.359, name/password entry <= 0.287; abstains without a series.
MIN_EVER_CHANGED = 0.32
# D: tile reuse inside one screen - drawn 8x8 tiles over distinct drawn 8x8
# tiles, on the *best* screen. A playfield is a small tile set repeated across
# the screen; a title card is a one-off bitmap whose tiles are nearly all
# unique; the maximum means one real gameplay screen clears the pack. Gameplay
# >= 2.52, a title card 1.28. A near-blank screen proves nothing, so it abstains.
MIN_TILE_REUSE = 1.9


def sheet_metrics(sheets):
    """`tileStructure` and `miscShare` from the loaded sheet sidecars."""
    grid = next((d for d in sheets.values() if d.get("kind") == "metatiles"), None)
    counted = {kind: sum(len(d.get("cells", [])) for d in sheets.values() if d.get("kind") == kind)
               for kind in ("metatiles", "hud", "font", "misc")}
    # F9.9 routes scene cells onto the captured screens, so what a sheet still
    # shows is no longer its share of the vocabulary. Counting only the remains
    # reads the routing as noise and inverts the answer - the better the routing
    # works, the more "off-grid" a pack looks (Zelda 1: menu-only at 33 %, with
    # 203 of its 231 scene cells routed). `routedCells` (ADR-0156) puts them back.
    counted["metatiles"] += sum(d.get("routedCells", 0) for d in sheets.values())
    total = sum(counted.values())
    return {
        "tileStructure": (grid or {}).get("gridConsistency", {}).get("alt8x8"),
        "miscShare": (counted["misc"] / total) if total else None,
    }


def evaluate(sheets, screen_dir):
    """{"verdict", "reasons", "metrics"} for one pack. `menu-only` when any
    clause fires, `unknown` when nothing could be measured at all."""
    metrics = sheet_metrics(sheets)
    metrics.update(screen_metrics(screen_dir))
    reasons = []
    structure, misc = metrics["tileStructure"], metrics["miscShare"]
    churn, reuse = metrics["everChanged"], metrics["reuse"]
    if structure is not None and structure < MIN_TILE_STRUCTURE:
        reasons.append("no repeating tile structure (%.2f < %.2f)" % (structure, MIN_TILE_STRUCTURE))
    if misc is not None and misc >= MAX_MISC_SHARE:
        reasons.append("%.0f%% of the vocabulary is off-grid noise" % (misc * 100))
    if churn is not None and churn < MIN_EVER_CHANGED:
        reasons.append("%d screens, only %.0f%% of the screen ever changes"
                       % (metrics["screens"], churn * 100))
    if reuse is not None and reuse < MIN_TILE_REUSE:
        reasons.append("screens are one-off bitmaps (tile reuse %.2f)" % reuse)
    if reasons:
        return {"verdict": "menu-only", "reasons": reasons, "metrics": metrics}
    if structure is None and reuse is None:
        return {"verdict": "unknown", "reasons": ["no metatiles.json and no readable screens"],
                "metrics": metrics}
    return {"verdict": "gameplay", "reasons": [], "metrics": metrics}


def probe(sheet_dir):
    """Evaluate the pack whose sheets live in `sheet_dir`."""
    sheets = {}
    for name in sorted(os.listdir(sheet_dir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(sheet_dir, name)) as handle:
                doc = json.load(handle)
        except (OSError, ValueError):
            continue
        if doc.get("version") == 1:
            sheets[name] = doc
    return evaluate(sheets, os.path.join(os.path.dirname(sheet_dir), "backgrounds"))


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    import sheet_report
    dirs = sheet_report.find_sheet_dirs(sys.argv[1])
    if not dirs:
        print("no sheets/ folder with sidecar JSON under %s" % sys.argv[1], file=sys.stderr)
        return 1
    results = [dict(probe(d), path=d) for d in dirs]
    if "--json" in sys.argv:
        json.dump(results, sys.stdout, indent=2)
        print()
    else:
        for result in results:
            # Tab-separated: a pack path can contain " - " (The Flintstones
            # does), so callers need a separator the data cannot forge.
            print("%s\t%s\t%s" % (result["verdict"], os.path.relpath(result["path"]),
                                   "; ".join(result["reasons"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
