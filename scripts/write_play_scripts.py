#!/usr/bin/env python3
"""Write the hand-tuned headless input scripts into a ROM library.

`scripts/bootstrap_auto_packs.sh` prefers `<lib>/<Game>/<Game>.play.txt` over
its generic Start/A masher. Those per-game scripts are the difference between
a pack recorded in a menu and a pack recorded in the game, but the library is
not version-controlled - so the sequences live here and are written out on
demand:

    python3 scripts/write_play_scripts.py "<roms-dir>"
    python3 scripts/write_play_scripts.py --list

Script format, read by `scripts/headless_record`'s `input=<file>`: one
`<seconds> <buttons>` step per line, buttons drawn from `UDLRABST`
(Select/sTart) or `-` for nothing held.

Every menu sequence below was found empirically, by recording a short probe
with `screenshot` and looking at the frame it ended on - not from memory of
how the game works. The comments say what each probe established, because
that is the part worth keeping: the button that moves a menu is rarely the
one you would guess.
"""

import argparse
import os
import sys

Step = str


def _repeat_until(intro, cycle, seconds):
    """intro, then cycle repeated until the script covers `seconds`."""
    out = list(intro)
    total = sum(float(s.split()[0]) for s in out)
    cycle_len = sum(float(s.split()[0]) for s in cycle)
    if cycle_len <= 0:
        return out
    while total < seconds:
        out += cycle
        total += cycle_len
    return out


def punch_out(seconds):
    # Start alone walks logo -> title -> circuit -> profile card -> the ring.
    # A or Right on the title types into the PASS KEY field instead, and the
    # generic script does exactly that: a 300 s recording that produced 12
    # captured screens, all of them the same password screen with one more
    # digit, `font` 0 and `hud` 0.
    intro = []
    for _ in range(16):
        intro += ["1.1 -", "0.2 T"]
    # In the ring Start throws the star uppercut, and between rounds or after
    # a knockdown it is what advances the screen - so it stays in the cycle.
    cycle = ["0.15 A", "0.25 -", "0.15 B", "0.25 -", "0.2 L", "0.2 -",
             "0.15 A", "0.25 -", "0.2 R", "0.2 -", "0.15 B", "0.3 -",
             "0.3 D", "0.2 -", "0.2 T", "0.3 -"]
    return _repeat_until(intro, cycle, seconds)


def _zelda_registration(title_wait):
    # REGISTER YOUR NAME is where every generic script died. The D-pad moves
    # the *alphabet* cursor; SELECT is what moves the heart between the file
    # rows and REGISTER/END. A script that only knows the D-pad types letters
    # forever - which is why both Zelda packs used to hold 69 near-identical
    # captures of this one screen.
    out = [f"{title_wait} -", "0.2 T", "2 -", "0.2 T", "2 -",
           "0.2 A", "0.4 -"]          # one letter, so the file has a name
    for _ in range(3):
        out += ["0.2 S", "0.6 -"]     # heart: file 1 -> 2 -> 3 -> REGISTER
    out += ["0.2 R", "0.5 -",         # REGISTER -> END
            "0.2 T", "2 -",           # confirm END, back to the file screen
            "0.2 T", "3 -"]           # start file 1
    return out


def zelda(seconds):
    # Overworld: walk a loop with the sword out. No Start - in game it opens
    # the subscreen and the recording would sit in the inventory.
    cycle = ["0.9 R", "0.2 -", "0.2 A", "0.3 -", "0.9 U", "0.2 -",
             "0.2 A", "0.3 -", "0.9 L", "0.2 -", "0.2 A", "0.3 -",
             "0.9 D", "0.2 -", "0.2 A", "0.3 -", "1.4 R", "0.2 A", "0.3 -",
             "1.4 U", "0.2 A", "0.3 -"]
    return _repeat_until(_zelda_registration(6), cycle, seconds)


def zelda_ii(seconds):
    # Same registration screen and the same SELECT rule. Right-heavy so the
    # side-scrolling screens actually scroll and the stitcher gets a sequence.
    cycle = ["1.6 R", "0.2 B", "0.2 -", "0.3 A", "0.2 -", "1.2 R",
             "0.2 B", "0.2 -", "0.6 U", "0.2 -", "1.2 R", "0.3 A", "0.2 -",
             "0.2 B", "0.3 -", "0.8 D", "0.2 -", "1.4 R", "0.2 B", "0.3 -"]
    return _repeat_until(_zelda_registration(8), cycle, seconds)


def excitebike(seconds):
    # The original hand-tuned script: two Starts into a race, then the wheelie
    # -> land -> accelerate rhythm that keeps the bike moving forward instead
    # of overheating. This is the recording that produces the continuous
    # 8224 px track, so treat its shape as the reference for a good one.
    intro = ["2 -", "0.2 T", "1 -", "0.2 T", "2 -"]
    cycle = ["1.2 A", "0.3 U", "0.8 B", "0.3 D", "1.2 A", "0.2 -"]
    return _repeat_until(intro, cycle, seconds)


SCRIPTS = {
    "Excitebike (1984) (Nintendo)": excitebike,
    "Mike Tyson's Punch-Out!! (1987) (Nintendo)": punch_out,
    "The Legend of Zelda (1987) (Nintendo)": zelda,
    "Zelda II - The Adventure of Link (1988) (Nintendo)": zelda_ii,
}

# Games known to need a script that does not exist yet. Recorded here so the
# next person does not re-derive the diagnosis.
KNOWN_UNSOLVED = {
    "Double Dragon (1988) (Technos)":
        "the title screen never advances - 75 s of Start, A, B and Select "
        "each leave it on the copyright screen, and it never falls through "
        "to an attract demo either. Not diagnosed: a bad dump and an "
        "emulation fault look the same from here. Needs a human with a "
        "reference build. Tracked as issue #163.",
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("library", nargs="?", help="ROM library directory")
    parser.add_argument("--seconds", type=float, default=300.0,
                        help="target script length (default: 300, matching "
                             "bootstrap_auto_packs.sh)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite a script that already exists. Off by "
                             "default: a script in the library may be "
                             "hand-tuned beyond what is reconstructed here, "
                             "and this tool has already destroyed one that "
                             "way.")
    parser.add_argument("--list", action="store_true",
                        help="list the games covered and exit")
    args = parser.parse_args(argv)

    if args.list:
        for name in sorted(SCRIPTS):
            print(f"  {name}")
        if KNOWN_UNSOLVED:
            print("\nknown unsolved:")
            for name, why in sorted(KNOWN_UNSOLVED.items()):
                print(f"  {name}\n    {why}")
        return 0

    if not args.library:
        parser.error("a library directory is required (or --list)")
    if not os.path.isdir(args.library):
        print(f"error: not a directory: {args.library}", file=sys.stderr)
        return 2

    written = skipped = 0
    for name, build in sorted(SCRIPTS.items()):
        folder = os.path.join(args.library, name)
        if not os.path.isdir(folder):
            # The pack folder is created by the bootstrap; without it this ROM
            # is not in this library, which is not an error.
            print(f"skip   {name} (no folder in the library)")
            skipped += 1
            continue
        path = os.path.join(folder, f"{name}.play.txt")
        if os.path.exists(path) and not args.force:
            print(f"keep   {name}.play.txt (exists; --force to replace)")
            skipped += 1
            continue
        steps = build(args.seconds)
        with open(path, "w") as handle:
            handle.write("\n".join(steps) + "\n")
        total = sum(float(s.split()[0]) for s in steps)
        print(f"wrote  {name}.play.txt ({len(steps)} steps, {total:.0f}s)")
        written += 1
    print(f"\n{written} written, {skipped} skipped, "
          f"{len(KNOWN_UNSOLVED)} known unsolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
