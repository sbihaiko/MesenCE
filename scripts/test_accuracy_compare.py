#!/usr/bin/env python3
"""Unit tests for the pure half of scripts/accuracy_compare.py (H10, ADR-0162).

Everything here runs without an emulator, without a ROM and without the
network: the recorder's `capture:` line is a string, the comparison is a dict,
and the perturbation is a text edit on a `hires.txt`. What needs a real core -
that the four arms actually produce the same frame - is the harness itself, and
is exercised by running it.

Usage: python3 scripts/test_accuracy_compare.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import accuracy_compare as ac  # noqa: E402

FAILURES = []


def check(condition, message):
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        FAILURES.append(message)


def raises(fn, exc, message):
    try:
        fn()
    except exc:
        check(True, message)
        return
    except Exception as other:  # noqa: BLE001 - the wrong exception is a failure, not a crash
        check(False, f"{message} (raised {type(other).__name__} instead)")
        return
    check(False, f"{message} (raised nothing)")


REAL_OUTPUT = """input script: /tmp/run-suite.txt (60070 frames)
ROM loaded: /tmp/AccuracyCoin.nes
emulated fps: 60.099 (master clock 1789773 Hz)
running 4808 frames for a final capture
capture: 256x240 frame=4808 pixels=61440 checksum=0xE5C1E0D8
capture borders: left=33 right=35 top=25 bottom=73 colour=0xFF4F4F4F blank=0
capture finished: 4809 frames (target 4808), 7.1s of wall clock
"""


def test_parse_capture():
    print("parse_capture")
    got = ac.parse_capture(REAL_OUTPUT)
    check(got == {"width": 256, "height": 240, "frame": 4808,
                  "pixels": 61440, "checksum": "E5C1E0D8"},
          "reads a real recorder run")
    check(ac.parse_capture("capture: 1x1 frame=1 pixels=1 checksum=0xdeadbeef")["checksum"] == "DEADBEEF",
          "checksum case is normalised, so 0xdeadbeef and 0xDEADBEEF are one value")
    # The load-bearing case: a run that produced no frame must not read as a
    # match. `capture failed:` goes to stderr, so stdout simply has no line.
    raises(lambda: ac.parse_capture("capture finished: 0 frames (target 4808)"),
           ValueError, "a run with no capture line raises instead of returning nothing")
    raises(lambda: ac.parse_capture("capture: 256x240 frame=4808 pixels=61440 checksum=0xE5C1E0"),
           ValueError, "a truncated checksum is not silently accepted")


def test_frames_to_seconds():
    print("frames_to_seconds")
    for frames in (1, 180, 4207, 4808, 18030, 60070):
        seconds = ac.frames_to_seconds(frames)
        check(round(seconds * ac.NTSC_FRAME_RATE) == frames,
              f"frame {frames} round-trips through the recorder's own conversion")
    raises(lambda: ac.frames_to_seconds(0), ValueError, "frame 0 is rejected")


def capture(checksum, frame=4808):
    return {"width": 256, "height": 240, "frame": frame, "pixels": 61440, "checksum": checksum}


def test_compare():
    print("compare")
    same = {(arm, "results-table"): capture("E5C1E0D8") for arm in ("vanilla", "builder", "hdpack", "mep")}
    check(ac.compare(same) == [], "four arms with one checksum is a pass")

    drifted = dict(same)
    drifted[("hdpack", "results-table")] = capture("DEADBEEF")
    divergences = ac.compare(drifted)
    check(len(divergences) == 1 and divergences[0]["arm"] == "hdpack",
          "one arm off the baseline is one divergence, named")
    check(divergences[0]["baseline"]["checksum"] == "E5C1E0D8"
          and divergences[0]["actual"]["checksum"] == "DEADBEEF",
          "the divergence carries both sides, so the report can print them")

    # A perturbation of the *baseline* must light up every other arm rather
    # than pass by moving the goalposts.
    moved = dict(same)
    moved[("vanilla", "results-table")] = capture("0BADF00D")
    check(len(ac.compare(moved)) == 3, "changing the baseline diverges the other three arms")

    # Equal checksums at different frames is not a match: it means one arm
    # stopped somewhere else, and comparing those two frames proves nothing.
    off_by_one = dict(same)
    off_by_one[("mep", "results-table")] = capture("E5C1E0D8", frame=4807)
    check(len(ac.compare(off_by_one)) == 1,
          "the same checksum at a different frame is still a divergence")

    check(ac.compare({("builder", "results-table"): capture("E5C1E0D8")})[0]["reason"].startswith("the baseline"),
          "no baseline capture is reported, never silently passed")

    two = dict(same)
    two[("vanilla", "boot-menu")] = capture("A69EB41A", frame=180)
    two[("builder", "boot-menu")] = capture("11111111", frame=180)
    divergences = ac.compare(two)
    check([d["checkpoint"] for d in divergences] == ["boot-menu"],
          "checkpoints are judged independently")


HIRES = """<ver>109
<scale>1
<supportedRom>1238072157A9641DAA5BAE54D3547451EB19CF05
<img>chr/Chr_00_0.png
<tile>0,01,2D003021,8,0,1,N
<tile>0,03,2D003021,24,0,1,N
<tile>0,04,2D003021,32,0,1,N
"""


def test_rotate_tile_art():
    print("rotate_tile_art")
    text, described = ac.rotate_tile_art(HIRES)
    lines = [l for l in text.splitlines() if l.startswith("<tile>")]
    # Art coordinates move one rule up; the tile index and palette - the match
    # keys - stay put, so the pack still replaces exactly the same tiles.
    check(lines == ["<tile>0,01,2D003021,24,0,1,N",
                    "<tile>0,03,2D003021,32,0,1,N",
                    "<tile>0,04,2D003021,8,0,1,N"],
          "every rule takes the next rule's (img, x, y), the last one wrapping to the first")
    check(text.splitlines()[:4] == HIRES.splitlines()[:4], "the header is untouched")
    check(described == "rotated the art of all 3 <tile> rules by one",
          "the description says how many rules it edited")
    check(ac.rotate_tile_art(ac.rotate_tile_art(text)[0])[0] == HIRES,
          "three rotations of three rules come back to the original")

    # A rotation that cannot change a pixel is not a perturbation. If every
    # rule points at one picture, or there is only one rule, the harness must
    # refuse rather than run a green "red" test.
    same_art = "<ver>109\n<tile>0,01,2D003021,8,0,1,N\n<tile>0,02,2D003021,8,0,1,N\n"
    raises(lambda: ac.rotate_tile_art(same_art), ValueError,
           "rules that all point at one picture are refused")
    raises(lambda: ac.rotate_tile_art("<ver>109\n<tile>0,01,2D003021,8,0,1,N\n"), ValueError,
           "a single rule is refused")
    raises(lambda: ac.rotate_tile_art("<ver>109\n<img>chr/Chr_00_0.png\n"), ValueError,
           "a pack with no tile rules is refused")


def test_resolve_rom(tmp):
    print("resolve_rom")
    present = tmp / "AccuracyCoin.nes"
    present.write_bytes(b"NES\x1a")
    other = tmp / "other.nes"
    other.write_bytes(b"NES\x1a")
    check(ac.resolve_rom(str(present), None, []) == present.resolve(), "--rom wins")
    check(ac.resolve_rom(None, str(present), []) == present.resolve(), "the env var is used when --rom is absent")
    check(ac.resolve_rom(None, None, [str(present)]) == present.resolve(), "the conventional path is the last resort")
    check(ac.resolve_rom(str(present), str(other), [str(other)]) == present.resolve(),
          "an explicit --rom is not overridden by the env var")
    check(ac.resolve_rom(str(tmp / "gone.nes"), None, [str(present)]) == present.resolve(),
          "a --rom that does not exist falls through rather than failing here")
    check(ac.resolve_rom(None, None, [str(tmp / "gone.nes")]) is None,
          "nothing on disk is None - the caller's SKIP path")
    check(ac.resolve_rom(None, None, [str(tmp)]) is None, "a directory is not a ROM")


def test_format_report():
    print("format_report")
    captures = {(arm, "results-table"): capture("E5C1E0D8") for arm in ("vanilla", "builder")}
    checkpoints = (("results-table", 4808),)
    passing = ac.format_report(captures, [], ["vanilla", "builder"], checkpoints)
    check("PASS" in passing and "0xE5C1E0D8" in passing, "a passing report shows the shared checksum")
    drifted = dict(captures)
    drifted[("builder", "results-table")] = capture("DEADBEEF")
    failing = ac.format_report(drifted, ac.compare(drifted), ["vanilla", "builder"], checkpoints)
    check("FAIL" in failing and "builder @ results-table" in failing and "0xDEADBEEF" in failing,
          "a failing report names the arm, the checkpoint and both checksums")


def test_arm_table():
    print("arm table")
    check(ac.BASELINE in ac.ARMS, "the baseline is one of the arms")
    check(all(set(spec) == {"install", "flags", "layer"} for spec in ac.ARMS.values()),
          "every arm declares install, flags and layer")
    check(ac.ARMS[ac.BASELINE]["install"] is None and ac.ARMS[ac.BASELINE]["flags"] == (),
          "the baseline turns no layer on - otherwise there is nothing to compare against")
    check({spec["install"] for spec in ac.ARMS.values()} <= {None, "hdpack", "mep"},
          "install kinds are the ones install_pack knows")


def main():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        test_parse_capture()
        test_frames_to_seconds()
        test_compare()
        test_rotate_tile_art()
        test_resolve_rom(tmp)
        test_format_report()
        test_arm_table()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
