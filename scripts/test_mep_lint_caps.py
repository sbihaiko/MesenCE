#!/usr/bin/env python3
"""mep_lint's per-member size cap (MAX_MEMBER_BYTES, ADR-0006/ADR-0138 §41
trust model): a zip whose central directory declares a member larger than
the cap must produce a lint *error* (verdict `invalid`), never inflate the
member or crash. zipfile derives file_size from the bytes it writes, so the
test lowers the constant to a few bytes instead of forging a header.

Also covers the same cap in classify_pack_brief's nested-zip open (it
notes the refusal in the brief instead of inflating), and that
Source.open()/read() raise MemberTooLargeError, a ValueError subclass.

Usage: python3 scripts/test_mep_lint_caps.py
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import classify_pack_brief  # noqa: E402
import mep_lint  # noqa: E402

FAILURES: list[str] = []
HIRES = "<ver>106\n<scale>1\n<img>tiles.png\n<img>big.png\n"
PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f8ffff3f0005fe02fea72d3e4a0000000049454e44ae426082"
)


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def _pack_zip(path: Path, big_member: bytes) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("textures/hires.txt", HIRES)
        zf.writestr("textures/tiles.png", PNG_1x1)
        zf.writestr("textures/big.png", big_member)


@contextlib.contextmanager
def _cap(value: int):
    saved = mep_lint.MAX_MEMBER_BYTES
    mep_lint.MAX_MEMBER_BYTES = value
    classify_pack_brief.MAX_MEMBER_BYTES = value
    try:
        yield
    finally:
        mep_lint.MAX_MEMBER_BYTES = saved
        classify_pack_brief.MAX_MEMBER_BYTES = saved


def _lint(path: Path) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = mep_lint.main(["mep_lint.py", str(path)])
    return rc, out.getvalue()


def check_source_read_raises(tmp: Path):
    zpath = tmp / "pack.zip"
    _pack_zip(zpath, b"x" * 64)
    src = mep_lint.Source(zpath)
    with _cap(50):
        for method in (src.read, src.open):
            try:
                method("textures/big.png")
            except mep_lint.MemberTooLargeError as exc:
                if not isinstance(exc, ValueError) or exc.rel != "textures/big.png" or exc.size != 64:
                    fail(f"MemberTooLargeError carries the wrong details: {exc!r}")
                    return
            else:
                fail(f"Source.{method.__name__} inflated a member over the cap")
                return
        if src.read("textures/hires.txt") != HIRES.encode():
            fail("a member under the cap must still be readable")
            return
    ok("Source.read/open raise MemberTooLargeError (a ValueError) for a member over MAX_MEMBER_BYTES")


def check_lint_error_not_crash(tmp: Path):
    zpath = tmp / "pack.zip"
    # A referenced PNG over the test cap; hires.txt and the 1x1 PNG stay under 100 bytes.
    _pack_zip(zpath, PNG_1x1 + b"\x00" * 200)
    rc, text = _lint(zpath)
    if rc != 0:
        fail(f"baseline pack must lint clean, got exit {rc}:\n{text}")
        return
    with _cap(100):
        rc, text = _lint(zpath)
    if rc != 1:
        fail(f"over-cap member must make the lint exit 1 (invalid), got {rc}:\n{text}")
        return
    if "error   textures/big.png" not in text or "over the 100-byte cap" not in text:
        fail(f"over-cap member must be reported as a lint error naming the member:\n{text}")
        return
    ok("a member over the cap is a lint error (verdict invalid), not an exception")


def check_nested_zip_over_cap(tmp: Path):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("textures/hires.txt", HIRES)
        zf.writestr("textures/tiles.png", PNG_1x1)
        zf.writestr("textures/big.png", PNG_1x1)
    outer = tmp / "container.zip"
    with zipfile.ZipFile(outer, "w") as zf:
        zf.writestr("readme.txt", "bonus")
        zf.writestr("real-pack.zip", inner.getvalue())
    rc, text = _lint(outer)
    if rc != 0:
        fail(f"nested-zip baseline must lint clean, got exit {rc}:\n{text}")
        return
    with _cap(100):
        rc, text = _lint(outer)
        brief = classify_pack_brief.build_brief(outer, None)
    if rc != 1 or "error   real-pack.zip" not in text:
        fail(f"nested zip over the cap must be a lint error on the nested member:\n{text}")
        return
    if "nested zip unreadable: real-pack.zip" not in brief or "over the 100-byte cap" not in brief:
        fail(f"classify brief must note the refused nested zip:\n{brief}")
        return
    if "textures/hires.txt" in brief:
        fail("classify brief inflated the over-cap nested zip")
        return
    ok("nested-zip fallback honours the cap in mep_lint (error) and classify_pack_brief (noted, not inflated)")


def main() -> int:
    if mep_lint.MAX_MEMBER_BYTES != 314572800:
        fail(f"MAX_MEMBER_BYTES must equal the 300 MB download cap, got {mep_lint.MAX_MEMBER_BYTES}")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        check_source_read_raises(tmp)
        check_lint_error_not_crash(tmp)
        check_nested_zip_over_cap(tmp)
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nall member-cap checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
