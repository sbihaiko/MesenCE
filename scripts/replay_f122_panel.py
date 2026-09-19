#!/usr/bin/env python3
"""Mechanical replay of the F12.2 "Copy as MEP sheet cell" panel script.

`docs/validation/f12.2-copy-sheet-cell-panel-script.md` is a *human* cold-read
panel: a person who did not build the feature finds the menu item, pastes one
cell and paints it without ever opening `textures/hires.txt`. This script does
NOT replace that run and cannot: discoverability, the P15 judgement and "did
they read hires.txt" are only measurable on a person.

What it does replace is the part a machine does better than a person: the
setup steps S1-S4, and the paste-and-paint round trip P9-P14, replayed end to
end until a magenta square is asserted in a real emulator screenshot. Its job
is to make sure the human run cannot be silently defeated by the environment -
every one of S1-S4 exists because a real attempt was defeated by it.

Per game the replay does exactly what the script tells the evaluator to do:

  P9/P10  append one cell to `textures/sheets/misc.json`, with the copied key
          as `tiles[0]` and three nulls
  P11     grow `misc.png` (and `misc.orig.png`) by a whole row when the sheet
          has no free slot - Contra does, Zelda does not
  P12     paint a 32x32 solid magenta square at the cell's top-left pixel
  P13     `python3 scripts/mep_build.py build <pack>`, which must exit 0, and
          must emit the pasted key as a `<tile>` whose x,y is the painted crop
  P14     install the pack to `<rom dir>/mep/`, reopen the ROM and assert the
          magenta actually reaches the screen

The key pasted in P10 stands in for P7's right-click. A machine cannot click a
tile, so the key is *measured* instead of guessed: a probe pass paints every
`metatiles` cell's first quadrant a colour that encodes the cell index, plays
the same route to the same frame, and reads back which cells the screen
actually draws. The key it returns is a tile that is provably on screen at the
frame the replay asserts against - which is what the evaluator's click gives
them, and what an invented key would not.

Usage:
    python3 scripts/replay_f122_panel.py [--game zelda|contra|both]
                                         [--out runs/f12.2-replay]
                                         [--roms <library>] [--panel ~/f12.2-panel]
                                         [--keep-install]
"""

import argparse
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import time
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sheet_repaint as _repaint  # noqa: E402  (same folder, stdlib-only)

REPO = pathlib.Path(__file__).resolve().parent.parent
MAGENTA = (255, 0, 255, 255)

#The ROM library is never in the repo. `--roms` overrides both of these, and
#MESEN_NES_ROMS is the same variable UI.HeadlessTests/CopyAsMepSheetCellTests.cs
#reads, so one export serves the headless test and this replay.
DEFAULT_ROMS = pathlib.Path(
    os.environ.get("MESEN_NES_ROMS")
    or "/Users/bihaiko/VSCodeProjects/EMULADORES/2. Switch/G3 - Nitendinho/roms")
DEFAULT_PANEL = pathlib.Path(
    os.environ.get("MESEN_F122_PANEL") or pathlib.Path.home() / "f12.2-panel")

#Per game: everything the panel script states in P3, P10, P11 and P12, plus the
#route and the frame the replay reopens the ROM at.
#
#`seconds` is the point on `route` whose frame the assertion is made against.
#It is not free: a frame the recording captured as a whole-screen
#`<background>` draws that PNG and ignores every `<tile>` rule, so a cell
#painted on such a screen can never show. The probe pass below is the gate that
#proves the chosen frame is not one of those; when it fails it says so rather
#than reporting a green run on a screen nothing could have changed.
GAMES = {
    "zelda": {
        "rom": "The Legend of Zelda (1987) (Nintendo).nes",
        "pack_dir": "The Legend of Zelda (1987) (Nintendo)",
        "panel_copy": "zelda",
        "route": ["The Legend of Zelda (1987) (Nintendo)/"
                  "The Legend of Zelda (1987) (Nintendo).play.txt"],
        "route_is_rom_relative": True,
        "seconds": 47,
        #P10 - slot 23 is free in a 5-wide sheet that holds 23 cells.
        "cell": {"index": 23, "x": 52, "y": 69},
        #P11 - nothing to resize.
        "grow": None,
        #P12
        "paint_at": (208, 276),
    },
    "contra": {
        "rom": "Contra (1988) (Konami).nes",
        "pack_dir": "Contra (1988) (Konami)",
        "panel_copy": "contra",
        "route": ["scripts/stages/contra/mint-stage1.txt",
                  "scripts/stages/contra/stage1-long.txt"],
        "route_is_rom_relative": False,
        "seconds": 22,
        #P10 - 4 full rows of 5 and no free slot, so the cell opens a fifth row.
        "cell": {"index": 20, "x": 1, "y": 69},
        #P11 - one whole row on both the sheet and its reference twin.
        "grow": {"sheet": (344, 344), "reference": (86, 86)},
        #P12
        "paint_at": (4, 276),
    },
}


class ReplayError(Exception):
    """A step the replay cannot honestly continue past."""


# --- small helpers -----------------------------------------------------------


def log(step: str, text: str) -> None:
    print(f"{step:<6} {text}", flush=True)


def run(cmd, cwd=REPO, timeout=1800):
    started = time.monotonic()
    proc = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True,
                          text=True, timeout=timeout)
    return proc, time.monotonic() - started


def png_size(path: pathlib.Path):
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ReplayError(f"{path}: not a PNG")
    return struct.unpack(">II", head[16:24])


def paint_square(path: pathlib.Path, x: int, y: int, size: int, rgba) -> None:
    img = _repaint.read_png(path)
    if x + size > img.width or y + size > img.height:
        raise ReplayError(f"{path}: {size}x{size} at {x},{y} falls outside "
                          f"{img.width}x{img.height}")
    for row in range(y, y + size):
        for col in range(x, x + size):
            off = img.offset(col, row)
            img.px[off:off + 4] = bytes(rgba)
    _repaint.write_png(path, img)


def grow_canvas(path: pathlib.Path, width: int, height: int) -> None:
    """P11's canvas growth: keep every existing pixel, add fully transparent
    rows. Transparent is not cosmetic - the builder calls a cell painted when
    the sheet differs from the upscaled reference twin, so new rows that match
    the (equally transparent) twin stay unpainted until someone paints them."""
    img = _repaint.read_png(path)
    if (img.width, img.height) == (width, height):
        return
    if img.width != width or img.height > height:
        raise ReplayError(f"{path}: cannot grow {img.width}x{img.height} to "
                          f"{width}x{height}")
    out = _repaint.Image(width, height)
    out.paste(img, 0, 0)
    _repaint.write_png(path, out)


def screenshot_colors(shot: pathlib.Path) -> Counter:
    img = _repaint.read_png(shot)
    return Counter(tuple(img.px[i * 4:i * 4 + 3])
                   for i in range(img.width * img.height))


# --- the emulator ------------------------------------------------------------


def record(ctx, game, out_prefix: pathlib.Path, seconds: int):
    """Reopen the ROM under `headless_record`, play the route to `seconds` and
    take the final screenshot. Returns (colors, tiles, stdout)."""
    tool = REPO / "scripts/headless_record"
    if not tool.exists():
        raise ReplayError("scripts/headless_record is not built - run "
                          "`make capture-tool` (see the build traps in "
                          "UI.HeadlessTests/AGENTS.md for the toolchain)")
    shutil.rmtree(out_prefix.parent, ignore_errors=True)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["caffeinate", "-dimsu", str(tool), str(ctx["roms"] / game["rom"]),
           str(seconds), str(out_prefix), "screenshot", "log",
           f"input={game['route_path']}"]
    proc, secs = run(cmd)
    if proc.returncode != 0:
        raise ReplayError(f"headless_record exited {proc.returncode}\n{proc.stdout[-2000:]}"
                          f"\n{proc.stderr[-2000:]}")
    tiles = None
    for line in proc.stdout.splitlines():
        if "LoadHdPack:" in line and "tiles=" in line:
            tiles = int(line.split("tiles=")[1].split()[0])
    shots = sorted((out_prefix.parent / "mesen-home/Screenshots").glob("*.png"))
    if not shots:
        raise ReplayError("headless_record took no screenshot")
    return screenshot_colors(shots[-1]), tiles, shots[-1], secs


def install(ctx, game, pack: pathlib.Path) -> pathlib.Path:
    """P14's first half. `<rom dir>/mep/` must be free before we start - S3
    renames the auto-installed community pack to `mep.off` precisely so that
    what renders is the pack under test and not somebody else's art."""
    mep = ctx["roms"] / game["pack_dir"] / "mep"
    if mep.exists() and not ctx["installed"]:
        raise ReplayError(f"{mep} already exists - S3 says it is renamed to "
                          "mep.off for the panel; refusing to overwrite it")
    shutil.rmtree(mep, ignore_errors=True)
    shutil.copytree(pack, mep)
    ctx["installed"] = True
    return mep


def uninstall(ctx, game) -> None:
    mep = ctx["roms"] / game["pack_dir"] / "mep"
    if ctx["installed"]:
        shutil.rmtree(mep, ignore_errors=True)
        ctx["installed"] = False


def build(pack: pathlib.Path):
    proc, secs = run(["caffeinate", "-dimsu", "python3", "scripts/mep_build.py",
                      "build", str(pack)])
    errors = [l for l in proc.stdout.splitlines() if l.startswith("error:")]
    return proc.returncode, errors, secs, proc.stdout


# --- S1-S4: the setup the evaluator never sees --------------------------------


def preconditions(ctx, game) -> list:
    """The four things that silently defeat the run, each as a pass/fail line."""
    results = []
    work = ctx["panel"] / game["panel_copy"]

    #S2 - work copies, not the live packs.
    live = ctx["roms"] / game["pack_dir"] / "auto"
    ok = work.is_dir() and (work / "textures/sheets/misc.json").is_file()
    results.append(("S2 work copy exists", ok, str(work)))
    results.append(("S2 work copy is not the live pack",
                    work.resolve() != live.resolve(), f"{work} vs {live}"))
    if not ok:
        return results

    #S1 - the pack must rebuild before anything is painted. A pack that refuses
    #here (ADR-0178) leaves the evaluator stuck at P13 with no way forward.
    scratch = ctx["out"] / game["panel_copy"] / "s1-baseline"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(work, scratch)
    rc, errors, secs, _ = build(scratch)
    results.append((f"S1 mep_build build exits 0 ({secs:.1f}s)", rc == 0,
                    "; ".join(errors[:3]) or "0 error(s)"))
    ctx.setdefault("baselines", {})[game["panel_copy"]] = scratch

    #S3 - the auto-installed community pack is moved aside, and nothing will
    #put it back while the panel runs.
    mep = ctx["roms"] / game["pack_dir"] / "mep"
    results.append(("S3 <rom dir>/mep moved aside", not mep.exists(), str(mep)))
    results.append(("S3 AutoInstallCommunityPacks is false", *auto_install_off()))

    #S4 - no stray pack in the *desktop* EnhancementPacks folder. The headless
    #tool runs against its own `mesen-home`, so this check is for the human run
    #in the real app; the `tiles=` evidence below is for both.
    results.append(("S4 EnhancementPacks holds no stray pack", *enhancement_packs_clean()))
    return results


def auto_install_off():
    settings = (pathlib.Path.home() /
                "Library/Application Support/MesenCE/settings.json")
    if not settings.is_file():
        return False, f"{settings} not found"
    #The file carries a UTF-8 BOM; read it as bytes and decode with utf-8-sig
    #rather than editing or rewriting it.
    doc = json.loads(settings.read_bytes().decode("utf-8-sig"))
    value = doc.get("EnhancementPacks", {}).get("AutoInstallCommunityPacks")
    return value is False, f"AutoInstallCommunityPacks={value!r}"


def enhancement_packs_clean():
    """A pack folder with no loadable `textures/hires.txt` can still match the
    ROM, win the textures section and leave the game dressed in nothing - the
    exact S4 failure. Flag any folder shaped like that; a folder with a real
    hires.txt is a submission, not a stray."""
    root = (pathlib.Path.home() /
            "Library/Application Support/MesenCE/EnhancementPacks")
    if not root.is_dir():
        return True, f"{root} does not exist"
    strays = [p.name for p in sorted(root.iterdir())
              if p.is_dir() and not p.name.startswith(".")
              and (p / "textures").is_dir()
              and not (p / "textures/hires.txt").is_file()]
    folders = [p.name for p in sorted(root.iterdir())
               if p.is_dir() and not p.name.startswith(".")]
    return not strays, (f"{len(folders)} folder(s), none is a textures stub"
                        if not strays
                        else "stub pack folder(s): " + ", ".join(strays))


# --- the probe: which tile is actually on screen ------------------------------


def probe_key(ctx, game):
    """Stand-in for P7's right-click, measured rather than guessed.

    Paints the first 8x8 quadrant of every `metatiles` cell with the colour
    (255, index>>8, index&255), rebuilds, reopens the ROM at the reference
    frame and reads the screenshot back. Every probe colour found names a cell
    the screen really draws; the one covering the most pixels wins, and its
    `tiles[0]` is the key the replay pastes.

    Finding none is a hard failure, not a fallback: it means the frame draws a
    captured `<background>` (or nothing from the pack at all), and any magenta
    assertion made against it afterwards would be meaningless."""
    #Copied from the pristine work copy, never from the already-built baseline:
    #`mep_build.py build` rewrites 12 sprite sheets in place (the flip-unbake
    #pass), and a second build over its own output refuses with 32 "#253"
    #errors. Every pack here is therefore built exactly once.
    pack = ctx["out"] / game["panel_copy"] / "probe"
    shutil.rmtree(pack, ignore_errors=True)
    shutil.copytree(ctx["panel"] / game["panel_copy"], pack)

    sidecar = pack / "textures/sheets/metatiles.json"
    doc = json.loads(sidecar.read_text())
    scale = _sheet_scale(pack / "textures/sheets/metatiles.png", doc)
    cells = [c for c in doc["cells"] if c.get("tiles") and c["tiles"][0]]
    colors = {}
    img = _repaint.read_png(pack / "textures/sheets/metatiles.png")
    for cell in cells:
        index = cell["index"]
        if index > 0xFFFF:
            continue
        rgba = (255, (index >> 8) & 0xFF, index & 0xFF, 255)
        colors[rgba[:3]] = cell
        x0, y0 = cell["x"] * scale, cell["y"] * scale
        for row in range(y0, y0 + 8 * scale):
            for col in range(x0, x0 + 8 * scale):
                off = img.offset(col, row)
                img.px[off:off + 4] = bytes(rgba)
    _repaint.write_png(pack / "textures/sheets/metatiles.png", img)

    rc, errors, secs, _ = build(pack)
    if rc != 0:
        raise ReplayError(f"probe build exited {rc}: {'; '.join(errors[:3])}")
    install(ctx, game, pack)
    seen, tiles, shot, _ = record(ctx, game,
                                  ctx["out"] / game["panel_copy"] / "probe-run/p",
                                  game["seconds"])
    uninstall(ctx, game)

    hits = [(count, rgb) for rgb, count in seen.items()
            if rgb in colors and count > 0]
    if not hits:
        raise ReplayError(
            f"no probe colour reached the screen at {game['seconds']}s of the "
            f"route ({shot}). The frame is drawn by a captured <background>, "
            "which overrides every <tile> rule, so no painted cell could ever "
            "show there. Pick a frame the recording did not capture as a whole "
            "screen.")
    hits.sort(reverse=True)
    count, rgb = hits[0]
    cell = colors[rgb]
    return {
        "tile": cell["tiles"][0]["tile"],
        "palette": cell["tiles"][0]["palette"],
        "source": f"metatiles cell {cell['index']}",
        "pixels": count,
        "visible_cells": len(hits),
        "tiles_loaded": tiles,
        "probe_shot": shot,
    }


def _sheet_scale(png: pathlib.Path, doc: dict) -> int:
    width, _ = png_size(png)
    columns = doc["columns"]
    cell = doc["cell"]["w"]
    gutter = doc.get("gutter", 1)
    unit = columns * (cell + gutter) + gutter
    if unit == 0 or width % unit:
        raise ReplayError(f"{png}: {width}px is not a whole multiple of the "
                          f"{unit}px the sidecar describes")
    return width // unit


# --- P9-P14 -------------------------------------------------------------------


def replay(ctx, game, key):
    out = {}
    pack = ctx["out"] / game["panel_copy"] / "painted"
    shutil.rmtree(pack, ignore_errors=True)
    shutil.copytree(ctx["panel"] / game["panel_copy"], pack)
    sheets = pack / "textures/sheets"

    #P9/P10 - append the cell, the copied key as tiles[0] and three nulls.
    doc = json.loads((sheets / "misc.json").read_text())
    spec = game["cell"]
    if any(c["index"] == spec["index"] for c in doc["cells"]):
        raise ReplayError(f"misc.json already holds a cell {spec['index']} - the "
                          "work copy is not pristine")
    doc["cells"].append({
        "index": spec["index"], "x": spec["x"], "y": spec["y"], "count": 1,
        "context": "misc",
        "tiles": [{"tile": key["tile"], "palette": key["palette"]}, None, None, None],
    })
    (sheets / "misc.json").write_text(json.dumps(doc, indent=1) + "\n")
    out["P10"] = f"cell {spec['index']} at {spec['x']},{spec['y']} appended"

    #P11 - grow the canvas by a whole row when the sheet has no free slot.
    before = png_size(sheets / "misc.png")
    if game["grow"]:
        grow_canvas(sheets / "misc.png", *game["grow"]["sheet"])
        grow_canvas(sheets / "misc.orig.png", *game["grow"]["reference"])
        out["P11"] = (f"misc.png {before[0]}x{before[1]} -> "
                      f"{game['grow']['sheet'][0]}x{game['grow']['sheet'][1]}, "
                      f"misc.orig.png -> {game['grow']['reference'][0]}x"
                      f"{game['grow']['reference'][1]}")
    else:
        out["P11"] = f"misc.png {before[0]}x{before[1]}, nothing to resize"

    #P12 - the 32x32 magenta square at the new cell's top-left pixel.
    px, py = game["paint_at"]
    paint_square(sheets / "misc.png", px, py, 32, MAGENTA)
    out["P12"] = f"32x32 magenta at {px},{py}"

    #P13 - build, and read the pasted key back out of hires.txt. That read-back
    #is the panel's criterion 5: the round trip is the key coming out as a
    #<tile> whose x,y is the painted crop.
    rc, errors, secs, _ = build(pack)
    out["P13"] = f"rc={rc}, {len(errors)} error(s), {secs:.0f}s"
    if rc != 0:
        raise ReplayError(f"mep_build build exited {rc}: {'; '.join(errors[:5])}")
    hires = (pack / "textures/hires.txt").read_text().splitlines()
    wanted = f",{key['tile']},{key['palette']},{px},{py},"
    roundtrip = [l for l in hires if wanted in l and "<tile>" in l]
    ungated = [l for l in roundtrip if not l.startswith("[")]
    out["P13 round-trip"] = (f"{len(roundtrip)} <tile> line(s), "
                             f"{len(ungated)} of them ungated")
    if not roundtrip:
        raise ReplayError(f"the pasted key never came back out of hires.txt "
                          f"as a <tile> at {px},{py}")
    out["P13 tile line"] = (ungated or roundtrip)[0]

    #Criterion 6 - lint stays clean.
    proc, _ = run(["python3", "scripts/mep_lint.py", str(pack)])
    out["lint"] = f"rc={proc.returncode}"

    #P14 - install, reopen the ROM, and look at the screen.
    baseline = ctx["baselines"][game["panel_copy"]]
    install(ctx, game, baseline)
    before_colors, before_tiles, before_shot, _ = record(
        ctx, game, ctx["out"] / game["panel_copy"] / "before/b", game["seconds"])
    uninstall(ctx, game)
    out["P14 baseline"] = (f"tiles={before_tiles}, magenta="
                           f"{before_colors[MAGENTA[:3]]}, {before_shot.name}")

    install(ctx, game, pack)
    after_colors, after_tiles, after_shot, _ = record(
        ctx, game, ctx["out"] / game["panel_copy"] / "after/a", game["seconds"])
    if not ctx["keep_install"]:
        uninstall(ctx, game)
    out["P14 painted"] = (f"tiles={after_tiles}, magenta="
                          f"{after_colors[MAGENTA[:3]]}, {after_shot.name}")
    out["P14 screenshot"] = str(after_shot)

    if before_colors[MAGENTA[:3]] != 0:
        raise ReplayError("the unpainted pack already renders magenta - the "
                          "assertion would prove nothing")
    if after_colors[MAGENTA[:3]] == 0:
        raise ReplayError("the painted cell never reached the screen: no "
                          f"magenta pixel in {after_shot}")
    out["P14"] = f"{after_colors[MAGENTA[:3]]} magenta pixels on screen"
    return out


# --- driver -------------------------------------------------------------------


def route_path(ctx, game) -> pathlib.Path:
    parts = []
    for entry in game["route"]:
        base = ctx["roms"] if game["route_is_rom_relative"] else REPO
        parts.append((base / entry).read_text())
    if len(parts) == 1 and game["route_is_rom_relative"]:
        return ctx["roms"] / game["route"][0]
    joined = ctx["out"] / f"{game['panel_copy']}-route.txt"
    joined.parent.mkdir(parents=True, exist_ok=True)
    joined.write_text("".join(parts))
    return joined


def replay_one(ctx, name) -> dict:
    game = dict(GAMES[name])
    game["panel_copy"] = GAMES[name]["panel_copy"]
    report = {"game": name, "ok": False, "steps": {}, "preconditions": []}
    try:
        report["preconditions"] = preconditions(ctx, game)
        for label, ok, detail in report["preconditions"]:
            log("setup", f"[{'PASS' if ok else 'FAIL'}] {label} - {detail}")
        blocking = [l for l, ok, _ in report["preconditions"]
                    if not ok and l.startswith(("S1", "S2", "S3 <rom"))]
        if blocking:
            raise ReplayError("blocking precondition(s): " + "; ".join(blocking))

        game["route_path"] = route_path(ctx, game)
        key = probe_key(ctx, game)
        report["key"] = key
        log("P7", f"key from {key['source']}: {key['tile']} / {key['palette']} "
                  f"({key['pixels']} px on screen, {key['visible_cells']} cells visible)")

        steps = replay(ctx, game, key)
        report["steps"] = steps
        for step, text in steps.items():
            log(step, text)
        report["ok"] = True
    except ReplayError as ex:
        report["error"] = str(ex)
        log("FAIL", str(ex))
    finally:
        if not ctx["keep_install"]:
            uninstall(ctx, game)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game", default="both", choices=["zelda", "contra", "both"])
    parser.add_argument("--roms", type=pathlib.Path, default=DEFAULT_ROMS)
    parser.add_argument("--panel", type=pathlib.Path, default=DEFAULT_PANEL)
    parser.add_argument("--out", type=pathlib.Path, default=REPO / "runs/f12.2-replay")
    parser.add_argument("--keep-install", action="store_true",
                        help="leave the painted pack in <rom dir>/mep/ instead of "
                             "removing it when the run finishes")
    parser.add_argument("--json", type=pathlib.Path,
                        help="also write the machine-readable report here")
    args = parser.parse_args(argv)

    ctx = {
        "roms": args.roms, "panel": args.panel, "out": args.out,
        "keep_install": args.keep_install, "installed": False, "baselines": {},
    }
    args.out.mkdir(parents=True, exist_ok=True)

    names = ["zelda", "contra"] if args.game == "both" else [args.game]
    reports = []
    for name in names:
        log("", f"=== {name} ===")
        reports.append(replay_one(ctx, name))

    log("", "=== summary ===")
    for report in reports:
        log("", f"{report['game']}: {'PASS' if report['ok'] else 'FAIL'}"
                f"{'' if report['ok'] else ' - ' + report.get('error', '')}")
    if args.json:
        args.json.write_text(json.dumps(reports, indent=2, default=str) + "\n")
    return 0 if all(r["ok"] for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
