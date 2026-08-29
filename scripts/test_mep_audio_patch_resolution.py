#!/usr/bin/env python3
"""Framework-free checks for ADR-0144 audio-patch resolution (run #103
false negatives). Two pipeline bugs turned audio-only packs whose .ips/.bps
patch IS present into pack:invalid:

  A. mep_lint.py resolves <patch>/<bgm>/<sfx> refs case-sensitively
     (`src.exists`), so a patch stored as `MusicPatch.ips` but referenced
     as `MUSICPATCH.ips` (how Windows-authored HDnes packs are shipped)
     reports "file does not exist" — the classifier then concludes the
     patch is absent and the ADR-0144 audio exception cannot apply.
  B. mep_lint.py never reports which .ips/.bps patches are present in the
     archive, so the classifier cannot know a patch exists unless hires.txt
     references it — it falls back to a manual byte-read of the outer zip
     that cannot see inside the nested game zip, and wrongly concludes
     "no patch".

Both fixes are verified here: case-insensitive ref resolution (mirroring
the existing <img> behavior) and a `bundled patch: <name> (present)` info
line in the lint report.

Usage: python3 scripts/test_mep_audio_patch_resolution.py
"""
from __future__ import annotations

import io
import sys
import tempfile
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import mep_lint  # noqa: E402

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def make_zip(entries: dict) -> bytes:
    """A synthetic zip from {inner_path: bytes}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in entries.items():
            z.writestr(path, data)
    return buf.getvalue()


SHA1 = "EA343F4E445A9050D4B4FBAC2C77D0693B1D0922"


def check_patch_case_insensitive():
    """AC-1 (bug A): a <patch> ref stored under a different capitalization
    than the actual file (MUSICPATCH.ips vs MusicPatch.ips — how Windows-
    authored HDnes packs ship) must NOT be reported as "file does not
    exist": the loader and macOS/Windows resolve case-insensitively, so the
    patch is present and ADR-0144 can redeem the audio section."""
    hires = b"<ver>105\n<bgm>0,1,Stage 1.ogg\n<patch>MUSICPATCH.ips," + SHA1.encode() + b"\n"
    src = mep_lint.Source.from_zip_bytes(
        make_zip({"hires.txt": hires, "MusicPatch.ips": b"PATCH..."}),
        label="smb.zip",
    )
    rep = mep_lint.Report()
    mep_lint.lint_nes_hires(src, "hires.txt", rep)
    missing = [m for _, _, m in rep.items if "file does not exist: MUSICPATCH.ips" in m]
    if missing:
        fail(f"case-mismatched patch wrongly reported missing: {missing!r}")
        return
    icase = [m for _, _, m in rep.items if "only exists as" in m and "MUSICPATCH.ips" in m]
    if not icase:
        fail(f"expected an icase 'only exists as' warning for MUSICPATCH.ips; items: {[m for _, _, m in rep.items]}")
        return
    ok("a case-mismatched <patch> ref counts as present (icase warning, not 'file does not exist')")


def check_audio_track_case_insensitive():
    """AC-2 (bug A, audio): a <bgm>/<sfx> ref whose track exists under a
    different capitalization is not "missing" — same rule as <img>."""
    hires = b"<ver>105\n<bgm>0,1,ogg/STAGE1.ogg\n<sfx>0,2,ogg/SFX.PICKUP.ogg\n"
    src = mep_lint.Source.from_zip_bytes(
        make_zip({"hires.txt": hires, "ogg/stage1.ogg": b"", "ogg/sfx.pickup.ogg": b""}),
        label="audio-icase.zip",
    )
    rep = mep_lint.Report()
    mep_lint.lint_nes_hires(src, "hires.txt", rep)
    missing = [m for _, _, m in rep.items if "file does not exist" in m]
    if missing:
        fail(f"case-mismatched audio tracks wrongly reported missing: {missing!r}")
        return
    ok("case-mismatched <bgm>/<sfx> tracks count as present")


def check_bundled_patch_reported():
    """AC-3 (bug B): the lint report lists the .ips/.bps patches present in
    the archive (even when hires.txt never references them) as
    'bundled patch: <name> (present)', so the classifier can apply the
    ADR-0144 audio exception without re-reading the raw archive."""
    hires = b"<ver>105\n<bgm>0,1,ogg/bgm-main.ogg\n"
    src = mep_lint.Source.from_zip_bytes(
        make_zip({"hires.txt": hires, "NEA-Game.bps": b"BPS1..."}),
        label="patched.zip",
    )
    rep = mep_lint.Report()
    mep_lint.scan_bundled_patches(src, rep)
    present = [m for _, _, m in rep.items if "bundled patch: NEA-Game.bps" in m]
    if not present:
        fail(f"bundled patch not reported; items: {[m for _, _, m in rep.items]}")
        return
    ok("an unreferenced .bps patch in the archive is reported as present")


def check_bundled_patch_inside_nested_zip():
    """AC-4 (bug B, nested): after main() unwraps a nested game zip, the
    scan reports the patch inside it — the exact repo-archive shape of run
    #103 (per-game pack_download.bin holds the nested zip)."""
    outer = make_zip({"super.mario.audio.zip": make_zip({
        "hires.txt": b"<ver>105\n<bgm>0,1,ogg/bgm.ogg\n",
        "MusicPatch.ips": b"PATCH...",
    })})
    src = mep_lint.Source.from_zip_bytes(outer, label="repo.zip")
    nested = mep_lint.find_top_level_nested_zip(src.names)
    if not nested:
        fail("expected a single top-level nested zip")
        return
    inner = mep_lint.Source.from_zip_bytes(src.read(nested), label=nested)
    rep = mep_lint.Report()
    mep_lint.scan_bundled_patches(inner, rep)
    present = [m for _, _, m in rep.items if "bundled patch:" in m]
    if present != ["bundled patch: MusicPatch.ips (present)"]:
        fail(f"nested patch not reported correctly; got {present!r}")
        return
    ok("a patch inside a nested game zip is reported as present")


def check_patch_name_with_comma():
    """AC-6 (bug C): a <patch> ref whose filename contains a comma (perfectly
    legal, and real — `Ice Climber (USA, Europe).bps`) is parsed by naive
    comma-splitting as three tokens and wrongly flagged '<patch> needs
    file,sha1'. The sha1 is the LAST comma-separated token; the filename is
    everything before it, commas included."""
    hires = b"<ver>105\n<patch>Ice Climber (USA, Europe).bps," + SHA1.encode() + b"\n"
    src = mep_lint.Source.from_zip_bytes(
        make_zip({"hires.txt": hires, "Ice Climber (USA, Europe).bps": b"BPS1..."}),
        label="icvs.zip",
    )
    rep = mep_lint.Report()
    mep_lint.lint_nes_hires(src, "hires.txt", rep)
    errs = [m for _, _, m in rep.items if "needs file,sha1" in m]
    if errs:
        fail(f"comma-in-name patch wrongly rejected: {errs!r}")
        return
    missing = [m for _, _, m in rep.items if "file does not exist" in m and "Ice Climber (USA, Europe).bps" in m]
    if missing:
        fail(f"comma-in-name patch wrongly reported missing: {missing!r}")
        return
    ok("a <patch> filename containing a comma parses correctly (sha1 = last token)")


def check_main_prints_bundled_patch():
    """AC-5 (integration): the full mep_lint.py main() run prints the
    bundled-patch line in its report output — the classifier reads exactly
    this text (the pipeline runs with --quiet), so the line must survive
    end to end even under --quiet, which otherwise strips `info` lines."""
    data = make_zip({"hires.txt": b"<ver>105\n<bgm>0,1,ogg/bgm-main.ogg\n", "NEA-Game.bps": b"BPS1..."})
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        out = io.StringIO()
        with redirect_stdout(out):
            code = mep_lint.main(["mep_lint.py", tmp, "--quiet"])
        if code != 0:
            fail(f"main() returned {code}; stdout:\n{out.getvalue()}")
            return
        if "bundled patch: NEA-Game.bps (present)" not in out.getvalue():
            fail(f"main() --quiet report lacks the bundled-patch line; stdout:\n{out.getvalue()}")
            return
    finally:
        Path(tmp).unlink(missing_ok=True)
    ok("main() report output (under --quiet) includes the bundled-patch line")


def main():
    check_patch_case_insensitive()
    check_audio_track_case_insensitive()
    check_bundled_patch_reported()
    check_bundled_patch_inside_nested_zip()
    check_patch_name_with_comma()
    check_main_prints_bundled_patch()

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
