#!/usr/bin/env python3
"""Unit tests for scripts/classify_pack_brief.py (stdlib only)."""
import io
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import classify_pack_brief  # noqa: E402


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg):
    print(f"PASS: {msg}")


def _tiny_zip(path: Path):
    hires = (
        "# Credits: Test Author\n"
        "<ver>108\n"
        "<scale>2\n"
        "<img>tiles.png\n"
        "<tile>1,2,3,4,tiles.png,0,0\n"
        "<bgm>0,1,theme.ogg\n"
        "<sfx>2,3,hit.ogg\n"
        "<patch>game.ips\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hires.txt", hires)
        z.writestr("tiles.png", b"\x89PNG\r\n\x1a\n")
        z.writestr("theme.ogg", b"OggS")
        z.writestr("hit.ogg", b"OggS")
        z.writestr("game.ips", b"PATCH" + b"\x00" * 8)
        z.writestr("README.txt", "Pack by Test Author\n")
    path.write_bytes(buf.getvalue())


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        zpath = tmp / "pack.zip"
        _tiny_zip(zpath)
        lint = tmp / "lint.txt"
        lint.write_text(
            "info    pack  bundled patch: game.ips (present)\n"
            "warning hires.txt:9  <background> missing.png does not exist — 1 entry dropped\n"
            "\n0 error(s), 1 warning(s) in pack.zip\n",
            encoding="utf-8",
        )
        brief = classify_pack_brief.build_brief(zpath, lint)
    if "hires.txt" not in brief:
        fail("brief missing hires.txt member")
    if "<img>=1" not in brief or "<bgm>=1" not in brief or "<sfx>=1" not in brief:
        fail(f"brief missing tag counts:\n{brief}")
    if "magic=ips" not in brief:
        fail("brief missing IPS magic")
    if "Test Author" not in brief:
        fail("brief missing credits excerpt")
    if "bundled patch: game.ips" not in brief:
        fail("brief missing lint bundled-patch line")
    if "does not exist" not in brief:
        fail("brief missing missing-file warning")
    if "0 error(s), 1 warning(s)" not in brief:
        fail("brief missing lint summary")
    if len(brief) > classify_pack_brief.MAX_BRIEF:
        fail("brief exceeds MAX_BRIEF")
    ok("classify_pack_brief.py emits a bounded inventory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
