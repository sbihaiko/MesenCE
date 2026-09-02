#!/usr/bin/env python3
"""Framework-free checks for mep_lint's border-section rules (ADR-0149 §1/§4,
Slice F8.3b).

Builds a tiny MEP pack in a temp dir (pack.json + border/border.png written
with zlib/struct, no fixture files under docs/), runs `mep_lint.main()` on it
and asserts on the exact error/warning messages the lint emits for
`border/border.png` and `border/border.json`.

Usage: python3 scripts/test_mep_lint_border.py
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import struct
import sys
import tempfile
import zlib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import mep_lint  # noqa: E402

LINE_RE = re.compile(r"^(error|warning|info)\s+(\S+)  (.*)$")

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def tiny_png(width=16, height=9):
    """Minimal valid RGBA PNG (IHDR + one zlib IDAT + IEND)."""
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x00\x00\x00\xff" * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


PACK_JSON = {
    "mep": "1.5.0",
    "name": "Border test",
    "version": "1.0.0",
    "id": "border-test",
    "license": "CC-BY-4.0",
    "targets": [{"system": "nes", "sha1": "0" * 40}],
    "sections": {"border": {"path": "border/"}},
}

GOOD_BORDER_JSON = {
    "version": 1,
    "width": 16,
    "height": 9,
    "viewport": {"x": 2, "y": 0, "width": 12, "height": 9},
    "scale_mode": "fit",
    "underlay": False,
}


def run_lint(border_png=b"__default__", border_json=None):
    """Writes the pack and returns (exit_code, [(level, where, msg), ...]).

    `border_png=None` omits the file; `border_json` is a dict, a raw string or
    None (omitted)."""
    with tempfile.TemporaryDirectory(prefix="mep_lint_border_") as tmp:
        root = Path(tmp) / "pack"
        (root / "border").mkdir(parents=True)
        (root / "pack.json").write_text(json.dumps(PACK_JSON), encoding="utf-8")
        if border_png == b"__default__":
            border_png = tiny_png()
        if border_png is not None:
            (root / "border" / "border.png").write_bytes(border_png)
        if border_json is not None:
            text = border_json if isinstance(border_json, str) else json.dumps(border_json)
            (root / "border" / "border.json").write_text(text, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = mep_lint.main(["mep_lint.py", str(root)])
        # mep_lint prints `f"{level:7s} {where}  {msg}"`: level padded to 7,
        # one space, path, two spaces, message.
        items = []
        for line in out.getvalue().splitlines():
            m = LINE_RE.match(line)
            if m:
                items.append((m.group(1), m.group(2), m.group(3)))
        return code, items


def errors(items):
    return [msg for level, _, msg in items if level == "error"]


def warnings(items):
    return [msg for level, _, msg in items if level == "warning"]


def expect_error(name, msg, **kwargs):
    code, items = run_lint(**kwargs)
    errs = errors(items)
    if code == 1 and msg in errs:
        ok(name)
    else:
        fail(f"{name}: expected exit 1 with error {msg!r}, got exit {code}, errors {errs!r}")


def check_valid_pack():
    code, items = run_lint(border_json=GOOD_BORDER_JSON)
    if code == 0 and not errors(items) and not warnings(items):
        ok("valid border pack (png + json) lints clean")
    else:
        fail(f"valid border pack: exit {code}, items {items!r}")
    infos = [msg for level, _, msg in items if level == "info"]
    if "border frame PNG 16x9" in infos:
        ok("border.png dimensions are reported as info")
    else:
        fail(f"expected 'border frame PNG 16x9' info, got {infos!r}")


def check_png_only_is_valid():
    code, items = run_lint()
    if code == 0 and not errors(items):
        ok("border.png without border.json lints clean (Core applies the default layout)")
    else:
        fail(f"png-only pack: exit {code}, items {items!r}")


def check_missing_png():
    expect_error("missing border.png is an error", "section 'border': 'border/border.png' does not exist", border_png=None)


def check_corrupt_png():
    expect_error("corrupt PNG (bad signature) is an error", "invalid or corrupt PNG file", border_png=b"not a png at all, just bytes...")
    expect_error("truncated PNG (signature only) is an error", "invalid or corrupt PNG file", border_png=b"\x89PNG\r\n\x1a\n")


def check_border_json_schema():
    code, items = run_lint(border_json="{nope")
    if code == 1 and any(e.startswith("invalid JSON: ") for e in errors(items)):
        ok("malformed border.json is an error")
    else:
        fail(f"malformed border.json: exit {code}, errors {errors(items)!r}")
    expect_error("border.json root not an object", "root must be an object", border_json=[1, 2])
    expect_error("viewport not an object", "'viewport' must be an object", border_json={**GOOD_BORDER_JSON, "viewport": [0, 0, 1, 1]})
    expect_error("viewport missing", "'viewport' is required", border_json={k: v for k, v in GOOD_BORDER_JSON.items() if k != "viewport"})
    expect_error("width missing", "'width' is required", border_json={k: v for k, v in GOOD_BORDER_JSON.items() if k != "width"})
    expect_error("height missing", "'height' is required", border_json={k: v for k, v in GOOD_BORDER_JSON.items() if k != "height"})
    expect_error("width zero", "'width' must be an integer > 0", border_json={**GOOD_BORDER_JSON, "width": 0})
    expect_error("height negative", "'height' must be an integer > 0", border_json={**GOOD_BORDER_JSON, "height": -9})
    expect_error("width float", "'width' must be an integer > 0", border_json={**GOOD_BORDER_JSON, "width": 16.5})
    expect_error("width string", "'width' must be an integer > 0", border_json={**GOOD_BORDER_JSON, "width": "16"})
    expect_error("width bool", "'width' must be an integer > 0", border_json={**GOOD_BORDER_JSON, "width": True})
    expect_error("viewport.x negative", "'viewport.x' must be an integer >= 0",
                 border_json={**GOOD_BORDER_JSON, "viewport": {"x": -1, "y": 0, "width": 12, "height": 9}})
    expect_error("viewport.width float", "'viewport.width' must be an integer >= 0",
                 border_json={**GOOD_BORDER_JSON, "viewport": {"x": 0, "y": 0, "width": 1.5, "height": 9}})
    expect_error("viewport.height missing", "'viewport.height' is required",
                 border_json={**GOOD_BORDER_JSON, "viewport": {"x": 0, "y": 0, "width": 12}})
    expect_error("bad scale_mode", "'scale_mode' must be \"fit\" or \"stretch\"", border_json={**GOOD_BORDER_JSON, "scale_mode": "zoom"})
    expect_error("scale_mode wrong case", "'scale_mode' must be \"fit\" or \"stretch\"", border_json={**GOOD_BORDER_JSON, "scale_mode": "Fit"})
    expect_error("non-bool underlay", "'underlay' must be a boolean", border_json={**GOOD_BORDER_JSON, "underlay": "true"})
    expect_error("integer underlay", "'underlay' must be a boolean", border_json={**GOOD_BORDER_JSON, "underlay": 1})


def check_stretch_and_underlay_accepted():
    code, items = run_lint(border_json={**GOOD_BORDER_JSON, "scale_mode": "stretch", "underlay": True})
    if code == 0 and not errors(items):
        ok("scale_mode=stretch + underlay=true lint clean")
    else:
        fail(f"stretch/underlay: exit {code}, items {items!r}")


def check_viewport_outside_canvas_warns():
    # ADR-0149 §4: exceeding the canvas is a warning, not an error (Core clamps).
    code, items = run_lint(border_json={**GOOD_BORDER_JSON, "viewport": {"x": 8, "y": 0, "width": 12, "height": 9}})
    warn = "'viewport' exceeds the canvas ('width' x 'height'); it will be clamped"
    if code == 0 and not errors(items) and warn in warnings(items):
        ok("viewport exceeding the canvas horizontally is a warning, exit 0")
    else:
        fail(f"viewport overflow (x): exit {code}, items {items!r}")
    code, items = run_lint(border_json={**GOOD_BORDER_JSON, "viewport": {"x": 0, "y": 1, "width": 12, "height": 9}})
    if code == 0 and warn in warnings(items):
        ok("viewport exceeding the canvas vertically is a warning")
    else:
        fail(f"viewport overflow (y): exit {code}, items {items!r}")
    # Exactly on the edge is fine
    code, items = run_lint(border_json={**GOOD_BORDER_JSON, "viewport": {"x": 4, "y": 0, "width": 12, "height": 9}})
    if code == 0 and not warnings(items):
        ok("viewport touching the canvas edge does not warn")
    else:
        fail(f"viewport on edge: exit {code}, items {items!r}")


def check_unknown_version_warns():
    code, items = run_lint(border_json={**GOOD_BORDER_JSON, "version": 2})
    if code == 0 and "unknown 'version' 2 (expected 1)" in warnings(items):
        ok("unknown border.json version is a warning")
    else:
        fail(f"version 2: exit {code}, items {items!r}")


def check_multiple_errors_reported_together():
    code, items = run_lint(border_json={"width": 0, "viewport": "x", "scale_mode": 3, "underlay": None})
    errs = set(errors(items))
    want = {
        "'width' must be an integer > 0",
        "'height' is required",
        "'viewport' must be an object",
        "'scale_mode' must be \"fit\" or \"stretch\"",
        "'underlay' must be a boolean",
    }
    if code == 1 and want <= errs:
        ok("every schema violation is reported in one pass")
    else:
        fail(f"combined violations: exit {code}, missing {want - errs!r}")


def check_lint_border_json_unit():
    # Direct unit call keeps the rule usable outside a pack (e.g. by other tools).
    rep = mep_lint.Report()
    mep_lint.lint_border_json(GOOD_BORDER_JSON, "border/border.json", rep)
    if rep.errors == 0 and rep.warnings == 0:
        ok("lint_border_json accepts the ADR-0149 example shape")
    else:
        fail(f"lint_border_json on good input: {rep.items!r}")
    rep = mep_lint.Report()
    mep_lint.lint_border_json("string", "border/border.json", rep)
    if rep.errors == 1 and rep.items[0][2] == "root must be an object":
        ok("lint_border_json rejects a non-object root with a single error")
    else:
        fail(f"lint_border_json on string: {rep.items!r}")


def main():
    check_valid_pack()
    check_png_only_is_valid()
    check_missing_png()
    check_corrupt_png()
    check_border_json_schema()
    check_stretch_and_underlay_accepted()
    check_viewport_outside_canvas_warns()
    check_unknown_version_warns()
    check_multiple_errors_reported_together()
    check_lint_border_json_unit()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nall border lint checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
