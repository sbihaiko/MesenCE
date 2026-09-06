#!/usr/bin/env python3
"""H10 (ADR-0162): does one of our layers change what the emulator computes?

This fork bolts three optional layers onto an accurate emulator - the HD Pack
Builder records tiles while the PPU runs, MEP replaces textures and audio, and
the Enhanced Synth taps the APU. Nothing tested whether turning one of them on
changes emulation. This does, and it does it *self-comparatively*: the same
accuracy suite is run against the same binary in several configurations and the
frames are required to be identical.

It is deliberately not a test of upstream's accuracy. The suite's own score
(AccuracyCoin reports 141/144 here) is upstream's business; what this asserts
is that the score, and every pixel around it, is the *same* number with our
layers active. A suite regression that is equally wrong in every arm passes.

The comparison primitive is the FNV-1a frame checksum of ADR-0159/F9.15
(`Core/Shared/Video/FrameCapture.h`), read off `scripts/headless_record`'s
`capture` flag at fixed absolute frames. That is sound here because the suite
prints its verdict on screen: AccuracyCoin's results table is 144 pass/fail
cells in one 256x240 frame, so a single checksum covers all of them. The run is
deterministic by ADR-0157 - input counted in emulated frames, zeroed power-on
RAM, and a run that ends on an absolute frame.

The two art-replacing arms use an **identity pack**: the HD pack the builder
itself records at scale 1 is installed and replayed. Every tile is replaced
(the core logs a 100 % match rate) with art that is a copy of what the PPU
would have drawn, so the replacement path is fully exercised and the correct
output is still bit-identical to vanilla. Without that trick a texture arm can
only be run with textures off, which tests almost nothing.

The suite ROM is not in this repo. AccuracyCoin is MIT-licensed
(https://github.com/100thCoin/AccuracyCoin) and could be vendored, but the
harness takes a path instead so it also works with a locally held suite, and
so no binary blob is carried here. With no ROM it prints SKIP and exits 0.

Usage:
  scripts/accuracy_compare.py [--rom PATH] [--work DIR] [--arms a,b,...]
                              [--json] [--require-rom] [--keep]
                              [--perturb-flag ARM=FLAG] [--perturb-texture ARM]

Exit codes: 0 pass or skip, 1 divergence, 2 harness/setup error.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORDER = REPO_ROOT / "scripts" / "headless_record"
NTSC_FRAME_RATE = 60.0988  # HeadlessInputScript::NtscFrameRate

# --- The suite profile -------------------------------------------------------
# Frame numbers are absolute and were read off real runs, not guessed:
#   180  - the boot menu ("CPU BEHAVIOR", page 1/22). Art on screen, no test
#          has run yet; this is the checkpoint an art layer would break first.
#   4808 - the results table ("TESTS PASSED: 141 / 144"). The table is first
#          drawn by frame 4207 and is static from there, so 4808 sits well
#          inside the settled window rather than on its edge.
# The input script presses Start once, which is AccuracyCoin's "run every
# test"; everything after that is the suite driving itself.
SUITE_NAME = "AccuracyCoin"
SUITE_FILE_SHA1 = "1238072157a9641daa5bae54d3547451eb19cf05"
SUITE_INPUT_SCRIPT = "# AccuracyCoin: run every test from the boot menu\n60f -\n10f T\n60000f -\n"
CHECKPOINTS = (("boot-menu", 180), ("results-table", 4808))

# --- The arms ----------------------------------------------------------------
# `install` says which identity pack the arm gets; `flags` are extra
# headless_record arguments. "vanilla" is the baseline every other arm is
# compared against.
BASELINE = "vanilla"
ARMS = {
    "vanilla": {"install": None, "flags": (), "layer": "none (baseline)"},
    "builder": {"install": None, "flags": ("hdpack",), "layer": "HD Pack Builder recording"},
    "hdpack": {"install": "hdpack", "flags": (), "layer": "loose HD pack, textures replaced"},
    "mep": {"install": "mep", "flags": (), "layer": "MEP container (textures + synth)"},
}

CAPTURE_RE = re.compile(
    r"^capture: (?P<width>\d+)x(?P<height>\d+) frame=(?P<frame>\d+) "
    r"pixels=(?P<pixels>\d+) checksum=0x(?P<checksum>[0-9A-Fa-f]{8})$",
    re.MULTILINE,
)


# --- Pure helpers (no emulator, no filesystem) -------------------------------

def parse_capture(stdout):
    """The `capture:` line of a headless_record run, as a dict.

    Raises ValueError when the run printed none - a run that never reached a
    decoded frame must not be mistaken for one that matched.
    """
    match = CAPTURE_RE.search(stdout)
    if not match:
        raise ValueError("no 'capture:' line in the recorder output")
    got = match.groupdict()
    return {
        "width": int(got["width"]),
        "height": int(got["height"]),
        "frame": int(got["frame"]),
        "pixels": int(got["pixels"]),
        "checksum": got["checksum"].upper(),
    }


def frames_to_seconds(frames, frame_rate=NTSC_FRAME_RATE):
    """The `<seconds>` argument that makes headless_record stop on `frames`.

    The recorder converts back with round(seconds * rate) (ADR-0157), so this
    is only correct if it round-trips; callers assert on the frame the capture
    reports anyway, which is the real guard.
    """
    if frames < 1:
        raise ValueError("a checkpoint must be at least frame 1")
    return frames / frame_rate


def compare(captures, baseline=BASELINE):
    """Divergences of every arm from the baseline, per checkpoint.

    `captures` maps (arm, checkpoint) -> the parse_capture dict. A missing
    baseline entry is an error, not a pass: nothing to compare against means
    nothing was compared.
    """
    checkpoints = sorted({cp for _, cp in captures}, key=lambda cp: cp)
    divergences = []
    for checkpoint in checkpoints:
        base = captures.get((baseline, checkpoint))
        if base is None:
            divergences.append({
                "arm": baseline, "checkpoint": checkpoint,
                "reason": "the baseline arm produced no capture at this checkpoint",
                "baseline": None, "actual": None,
            })
            continue
        for arm, cp in sorted(captures):
            if cp != checkpoint or arm == baseline:
                continue
            actual = captures[(arm, cp)]
            if actual["checksum"] == base["checksum"] and actual["frame"] == base["frame"]:
                continue
            divergences.append({
                "arm": arm, "checkpoint": checkpoint,
                "reason": "frame checksum differs from the baseline",
                "baseline": base, "actual": actual,
            })
    return divergences


def rotate_tile_art(hires_text):
    """Make every replaced tile render the *next* rule's picture, for
    --perturb-texture.

    A `<tile>` line is `<tile>img,tileIndex,palette,x,y,alpha,transparency`,
    where (img, x, y) says where the replacement art is. Rotating that triple
    by one across every rule keeps the file structurally valid - same rules,
    same images, every target still resolves - and changes only what is drawn.

    It rotates all of them rather than swapping a chosen pair because which
    pair is *on screen* at a checkpoint is not knowable from the manifest: the
    first attempt swapped two rules whose tiles AccuracyCoin never draws at
    either checkpoint, and the harness stayed green on a pack that had in fact
    been tampered with. Deleting rules would not work either - the identity
    pack's art is a copy of the PPU's own output, so a tile that falls back to
    the PPU still produces the same pixel.

    Returns (text, description), and raises when the rotation would be a no-op
    (fewer than two rules, or every rule pointing at one picture): a
    perturbation that cannot go red proves nothing.
    """
    lines = hires_text.splitlines(keepends=True)
    rules = []
    for index, line in enumerate(lines):
        if not line.startswith("<tile>"):
            continue
        fields = line[len("<tile>"):].rstrip("\r\n").split(",")
        if len(fields) >= 5:
            rules.append((index, fields))
    art = [(fields[0], fields[3], fields[4]) for _, fields in rules]
    if len(rules) < 2 or len(set(art)) < 2:
        raise ValueError("hires.txt has fewer than two <tile> rules pointing at distinct art")
    for position, (index, fields) in enumerate(rules):
        fields[0], fields[3], fields[4] = art[(position + 1) % len(art)]
        lines[index] = "<tile>" + ",".join(fields) + "\n"
    return "".join(lines), f"rotated the art of all {len(rules)} <tile> rules by one"


def resolve_rom(explicit, env_value, default_paths):
    """Where the suite ROM is, or None. First existing of: --rom, the
    MESENCE_ACCURACY_ROM env var, then the conventional paths."""
    for candidate in [explicit, env_value, *default_paths]:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    return None


def format_report(captures, divergences, arms, checkpoints):
    """The text table the caller reads."""
    out = [f"suite: {SUITE_NAME}", ""]
    width = max(len(a) for a in arms)
    header = "arm".ljust(width) + "  " + "  ".join(name.ljust(14) for name, _ in checkpoints)
    out.append(header)
    out.append("-" * len(header))
    for arm in arms:
        cells = []
        for name, _ in checkpoints:
            got = captures.get((arm, name))
            cells.append(("0x" + got["checksum"] if got else "-").ljust(14))
        out.append(arm.ljust(width) + "  " + "  ".join(cells))
    out.append("")
    if not divergences:
        out.append(f"PASS - every arm matches '{BASELINE}' at every checkpoint")
    else:
        out.append(f"FAIL - {len(divergences)} divergence(s) from '{BASELINE}':")
        for div in divergences:
            base = div["baseline"]
            actual = div["actual"]
            detail = ""
            if base and actual:
                detail = (f" (baseline 0x{base['checksum']} at frame {base['frame']},"
                          f" arm 0x{actual['checksum']} at frame {actual['frame']})")
            out.append(f"  {div['arm']} @ {div['checkpoint']}: {div['reason']}{detail}")
    return "\n".join(out)


# --- Running the emulator ----------------------------------------------------

def run_recorder(rom, out_prefix, frames, flags, script_path):
    """One headless_record run, returning its parsed capture."""
    cmd = [str(RECORDER), str(rom), f"{frames_to_seconds(frames):.6f}", str(out_prefix),
           "capture", f"input={script_path}", *flags]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"recorder failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}")
    capture = parse_capture(proc.stdout)
    if capture["frame"] != frames:
        raise RuntimeError(f"asked for frame {frames}, the capture reports {capture['frame']}")
    return capture


def record_identity_pack(rom, work, script_path, frames):
    """The HD pack the builder records over the whole compared range - the art
    the two replacement arms then replay."""
    stage = work / "prep"
    stage.mkdir(parents=True, exist_ok=True)
    run_recorder(rom, stage / "rec", frames, ("hdpack",), script_path)
    pack = stage / "rec-hdpack"
    if not (pack / "hires.txt").is_file():
        raise RuntimeError(f"the builder wrote no hires.txt in {pack}")
    return pack


def install_pack(kind, pack, home, rom):
    """Put the identity pack where the arm's layer will find it, and return the
    installed hires.txt (what --perturb-texture edits)."""
    if kind == "hdpack":
        target = home / "HdPacks" / rom.stem
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(pack, target, dirs_exist_ok=True)
        return target / "hires.txt"
    if kind == "mep":
        packs = home / "EnhancementPacks"
        packs.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "gen_mep_test_pack.py"),
             str(rom), str(packs), "dir", f"--textures={pack}"],
            check=True, capture_output=True, text=True)
        found = sorted(packs.glob("*/textures/hires.txt"))
        if not found:
            raise RuntimeError(f"gen_mep_test_pack.py wrote no textures/hires.txt under {packs}")
        return found[0]
    raise ValueError(f"unknown pack kind: {kind}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rom", help=f"the {SUITE_NAME} ROM (default: $MESENCE_ACCURACY_ROM, then tests/accuracy/)")
    parser.add_argument("--work", help="working directory (default: a temporary one)")
    parser.add_argument("--arms", default=",".join(ARMS), help="comma-separated subset of: " + ", ".join(ARMS))
    parser.add_argument("--json", action="store_true", help="machine-readable result on stdout")
    parser.add_argument("--require-rom", action="store_true", help="exit 2 instead of skipping when the ROM is absent")
    parser.add_argument("--keep", action="store_true", help="keep the working directory")
    parser.add_argument("--perturb-flag", action="append", default=[], metavar="ARM=FLAG",
                        help="append a headless_record flag to one arm (to prove the comparison can fail)")
    parser.add_argument("--perturb-texture", action="append", default=[], metavar="ARM",
                        help="swap two tile rules in one arm's installed pack (same purpose)")
    args = parser.parse_args(argv)

    rom = resolve_rom(args.rom, os.environ.get("MESENCE_ACCURACY_ROM"),
                      [REPO_ROOT / "tests" / "accuracy" / f"{SUITE_NAME}.nes"])
    if rom is None:
        message = (f"SKIP: no {SUITE_NAME} ROM. Pass --rom, set MESENCE_ACCURACY_ROM, or put it in "
                   f"tests/accuracy/{SUITE_NAME}.nes (MIT, https://github.com/100thCoin/AccuracyCoin).")
        print(json.dumps({"status": "skipped", "reason": message}) if args.json else message)
        return 2 if args.require_rom else 0
    if not RECORDER.is_file():
        print(f"error: {RECORDER} is missing - run `make capture-tool` first.", file=sys.stderr)
        return 2

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for arm in args.perturb_texture:
        if arm not in ARMS or not ARMS[arm]["install"]:
            print(f"error: --perturb-texture needs an arm that installs a pack, got '{arm}'", file=sys.stderr)
            return 2
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        print(f"error: unknown arm(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    if BASELINE not in arms:
        print(f"error: the '{BASELINE}' arm is the baseline and cannot be dropped", file=sys.stderr)
        return 2

    perturb_flags = {}
    for spec in args.perturb_flag:
        arm, _, flag = spec.partition("=")
        if arm not in ARMS or not flag:
            print(f"error: --perturb-flag wants ARM=FLAG, got '{spec}'", file=sys.stderr)
            return 2
        perturb_flags.setdefault(arm, []).append(flag)

    work = Path(args.work).resolve() if args.work else Path(tempfile.mkdtemp(prefix="accuracy-compare-"))
    work.mkdir(parents=True, exist_ok=True)
    script_path = work / "run-suite.txt"
    script_path.write_text(SUITE_INPUT_SCRIPT, encoding="utf-8")
    max_frame = max(frame for _, frame in CHECKPOINTS)
    notes = []
    # The checkpoints are frame numbers read off this exact ROM; against a
    # different build of the suite they would point at different screens.
    actual_sha1 = hashlib.sha1(rom.read_bytes()).hexdigest()  # noqa: S324 - No-Intro identity hash is SHA-1 by contract (ADR-0003/ADR-0039)
    if actual_sha1 != SUITE_FILE_SHA1:
        notes.append(f"WARNING: {rom.name} is sha1 {actual_sha1}, not the {SUITE_FILE_SHA1} the "
                     f"checkpoints were read from - the frame numbers may land on other screens")

    try:
        pack = None
        if any(ARMS[a]["install"] for a in arms):
            pack = record_identity_pack(rom, work, script_path, max_frame)
            notes.append(f"identity pack recorded by the builder over {max_frame} frames")

        captures = {}
        for arm in arms:
            spec = ARMS[arm]
            arm_dir = work / arm
            home = arm_dir / "mesen-home"
            home.mkdir(parents=True, exist_ok=True)
            if spec["install"]:
                hires = install_pack(spec["install"], pack, home, rom)
                if arm in args.perturb_texture:
                    text, described = rotate_tile_art(hires.read_text(encoding="utf-8"))
                    hires.write_text(text, encoding="utf-8")
                    notes.append(f"PERTURBED {arm}: {described}")
            flags = tuple(spec["flags"]) + tuple(perturb_flags.get(arm, ()))
            if arm in perturb_flags:
                notes.append(f"PERTURBED {arm}: extra recorder flag(s) {' '.join(perturb_flags[arm])}")
            for name, frame in CHECKPOINTS:
                captures[(arm, name)] = run_recorder(rom, arm_dir / f"out-{name}", frame, flags, script_path)
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    finally:
        if not args.keep and not args.work:
            shutil.rmtree(work, ignore_errors=True)

    divergences = compare(captures)
    if args.json:
        print(json.dumps({
            "status": "fail" if divergences else "pass",
            "rom": str(rom), "arms": arms, "notes": notes,
            "captures": {f"{arm}/{cp}": got for (arm, cp), got in sorted(captures.items())},
            "divergences": divergences,
        }, indent=2))
    else:
        for note in notes:
            print(note)
        print(format_report(captures, divergences, arms, CHECKPOINTS))
    return 1 if divergences else 0


if __name__ == "__main__":
    sys.exit(main())
