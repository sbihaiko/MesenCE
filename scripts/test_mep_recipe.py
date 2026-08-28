#!/usr/bin/env python3
"""Framework-free checks for scripts/mep_recipe.py (F6.1).

Acceptance (PRD slice F6.1):
  * unknown op is rejected
  * escaping path is rejected
  * dry-run of a synthetic split pack produces a mep_lint-clean pack

Also covers: golden recipe validates; apply_patch_only_if_complete withholds
the patch when a user_supplied dep is missing; wrapped primary zip is
opened through mep_lint discovery (not a parallel walker).

Usage: python3 scripts/test_mep_recipe.py
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
GOLDEN = ROOT / "docs" / "specs" / "golden" / "mep-recipe" / "recipe.json"

sys.path.insert(0, str(SCRIPTS))
import mep_lint  # noqa: E402
import mep_recipe  # noqa: E402

FAILURES = []
SHA1 = "2A4E126D0286BEA0BF503C80A12352C57539F76B"
SHAPE = "3C004200B900A500B900A50042003C00"
PAL = "0F001A2C"


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def png_rgba(width=8, height=8, rgba=(200, 40, 40, 255)) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgba) * width for _ in range(height))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


HIRES = "\n".join([
    "<ver>107",
    "<scale>1",
    "<img>tiles.png",
    f"<tile>0,{SHAPE},{PAL},0,0,1,N",
    "<bgm>0,0,theme.ogg",
    "<sfx>0,1,jump.ogg",
    f"<patch>game.ips,{SHA1}",
    "",
])
IPS = b"PATCHEOF"
PNG = png_rgba()
OGG_THEME = b"OggS\x00theme"
OGG_JUMP = b"OggS\x00jump"


def write_zip(path: Path, files: dict) -> str:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_recipe(primary_hash: str, audio_hash: str) -> dict:
    return {
        "recipe": 1,
        "sources": {
            "primary": {
                "url": "https://example.org/packs/synthetic-split-1.0.0.zip",
                "sha256": primary_hash,
            },
            "deps": [
                {
                    "id": "audio",
                    "sha256": audio_hash,
                    "size": 64,
                    "hints": ["https://example.org/audio/synthetic-split-ogg.zip"],
                    "license": "CC0-1.0",
                    "user_supplied": True,
                }
            ],
        },
        "ops": [
            {"op": "copy", "from": "primary:hires.txt", "to": "hires.txt"},
            {"op": "copy", "from": "primary:tiles.png", "to": "tiles.png"},
            {"op": "copy", "from": "primary:game.ips", "to": "game.ips"},
            {"op": "copy", "from": "primary:game.ips", "to": "patches/game.ips"},
            {"op": "glob", "from": "audio:**/*.ogg", "to": "audio/"},
            {"op": "rewrite-paths", "file": "hires.txt", "tags": ["bgm", "sfx"], "prefix": "audio/"},
        ],
        "pack": {
            "mep": "1.1.0",
            "name": "Synthetic Split Pack",
            "version": "1.0.0",
            "license": "CC0-1.0",
            "targets": [{"system": "nes", "sha1": SHA1}],
            "patches": [{"sha1": SHA1, "file": "patches/game.ips"}],
            "sections": {"textures": {"path": ""}},
        },
        "policy": {"apply_patch_only_if_complete": True},
    }


def check_golden_validates():
    recipe = json.loads(GOLDEN.read_text(encoding="utf-8"))
    errors = mep_recipe.validate_recipe(recipe)
    if errors:
        fail("golden recipe.json did not validate: " + "; ".join(errors))
        return
    rc = mep_recipe.main(["mep_recipe.py", "validate", str(GOLDEN)])
    if rc != 0:
        fail(f"mep_recipe.py validate golden exited {rc}")
        return
    ok("golden recipe.json validates")


def check_unknown_op_rejected():
    recipe = json.loads(GOLDEN.read_text(encoding="utf-8"))
    recipe["ops"].append({"op": "shell", "from": "primary:hires.txt", "to": "x"})
    errors = mep_recipe.validate_recipe(recipe)
    if not any("unknown op" in e for e in errors):
        fail(f"unknown op was not rejected: {errors}")
        return
    ok("unknown op rejected")


def check_escaping_path_rejected():
    recipe = json.loads(GOLDEN.read_text(encoding="utf-8"))
    recipe["ops"][0]["to"] = "../evil.txt"
    errors = mep_recipe.validate_recipe(recipe)
    if not any("escaping" in e for e in errors):
        fail(f"escaping path was not rejected: {errors}")
        return
    recipe = json.loads(GOLDEN.read_text(encoding="utf-8"))
    recipe["ops"][0]["from"] = "primary:../evil.txt"
    errors = mep_recipe.validate_recipe(recipe)
    if not any("escaping" in e for e in errors):
        fail(f"escaping source path was not rejected: {errors}")
        return
    ok("escaping path rejected")


def _make_split(tmp: Path, wrap_primary=False):
    primary_files = {
        "hires.txt": HIRES.encode("utf-8"),
        "tiles.png": PNG,
        "game.ips": IPS,
    }
    if wrap_primary:
        primary_files = {f"Release-v1/{name}": data for name, data in primary_files.items()}
    primary = tmp / "primary.zip"
    audio = tmp / "audio.zip"
    primary_hash = write_zip(primary, primary_files)
    audio_hash = write_zip(audio, {"theme.ogg": OGG_THEME, "folder/jump.ogg": OGG_JUMP})
    recipe = base_recipe(primary_hash, audio_hash)
    recipe_path = tmp / "recipe.json"
    recipe_path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
    return recipe_path, primary, audio, recipe


def check_dry_run_lint_clean():
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        recipe_path, primary, audio, _recipe = _make_split(tmp)
        out = tmp / "out"
        rc = mep_recipe.main([
            "mep_recipe.py", "dry-run", str(recipe_path),
            "--primary", str(primary),
            "--dep", f"audio={audio}",
            "--out", str(out),
        ])
        if rc != 0:
            fail(f"dry-run exited {rc}")
            return
        hires = (out / "hires.txt").read_text(encoding="utf-8")
        if "<bgm>0,0,audio/theme.ogg" not in hires or "<sfx>0,1,audio/jump.ogg" not in hires:
            fail(f"rewrite-paths did not prefix audio/: {hires!r}")
            return
        if not (out / "audio" / "theme.ogg").exists() or not (out / "audio" / "jump.ogg").exists():
            fail("glob did not copy oggs into audio/ by basename")
            return
        if not (out / "pack.json").exists():
            fail("dry-run did not write pack.json")
            return
        lint_rc = mep_lint.main(["mep_lint.py", str(out), "--quiet"])
        if lint_rc != 0:
            fail(f"dry-run output failed mep_lint.py (exit {lint_rc})")
            return
        ok("dry-run of a synthetic split pack is mep_lint-clean")


def check_wrapped_primary_uses_lint_discovery():
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        recipe_path, primary, audio, _recipe = _make_split(tmp, wrap_primary=True)
        out = tmp / "out"
        rc = mep_recipe.main([
            "mep_recipe.py", "apply", str(recipe_path),
            "--primary", str(primary),
            "--dep", f"audio={audio}",
            "--out", str(out),
        ])
        if rc != 0:
            fail(f"apply of wrapped primary exited {rc}")
            return
        if not (out / "hires.txt").exists():
            fail("wrapped primary was not opened at the discovered subfolder")
            return
        ok("wrapped primary zip uses mep_lint fallback discovery")


def check_incomplete_withholds_patch():
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        recipe_path, primary, _audio, recipe = _make_split(tmp)
        out = tmp / "out"
        mep_recipe.run_recipe(recipe, primary, deps={}, out=out, rom_name=None)
        if (out / "patches" / "game.ips").exists():
            fail("missing dep still copied the patch")
            return
        pack = json.loads((out / "pack.json").read_text(encoding="utf-8"))
        if pack.get("patches"):
            fail("incomplete install still wrote pack.patches")
            return
        if not (out / "hires.txt").exists() or not (out / "tiles.png").exists():
            fail("incomplete install dropped textures")
            return
        ok("apply_patch_only_if_complete withholds the patch when a dep is missing")


def check_hash_mismatch_aborts():
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        recipe_path, primary, audio, recipe = _make_split(tmp)
        recipe["sources"]["primary"]["sha256"] = "0" * 64
        out = tmp / "out"
        try:
            mep_recipe.run_recipe(recipe, primary, deps={"audio": audio}, out=out, rom_name=None)
        except mep_recipe.RecipeError as exc:
            if "sha256 mismatch" not in str(exc):
                fail(f"hash mismatch raised the wrong error: {exc}")
                return
            ok("primary sha256 mismatch aborts")
            return
        fail("primary sha256 mismatch did not abort")


def main():
    check_golden_validates()
    check_unknown_op_rejected()
    check_escaping_path_rejected()
    check_dry_run_lint_clean()
    check_wrapped_primary_uses_lint_discovery()
    check_incomplete_withholds_patch()
    check_hash_mismatch_aborts()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nAll mep_recipe checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
