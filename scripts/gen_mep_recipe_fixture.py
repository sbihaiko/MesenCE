#!/usr/bin/env python3
"""Generates the real-bytes MEP-recipe-v1 golden fixture (F6.4a).

The existing `docs/specs/golden/mep-recipe/recipe.json` is format-only: its
`sha256` fields are literally the sha256 of the empty string, per
MEP-recipe-v1 §9 ("not hashes of a committed zip"). Verifying that an
installer's output tree matches `scripts/mep_recipe.py apply`'s byte-for-byte
needs a fixture with real archive bytes and sha256 hashes that actually
match those bytes -- that is what this script produces, mirroring the
`_make_split`/`write_zip` pattern of `scripts/test_mep_recipe.py`.

Writes, under `docs/specs/golden/mep-recipe/fixture/`:
  primary.zip              -- hires.txt (bgm/sfx/patch tags) + tiles.png + game.ips
  audio-dep.zip             -- the "audio" dependency's real .ogg bytes
  recipe.json               -- full-deps recipe document, real sha256 hashes
  recipe-missing-dep.json   -- the same recipe document, used against an
                               incomplete dep map (the "audio" dep path
                               withheld at apply time) to exercise the
                               apply_patch_only_if_complete skip semantics
                               (MEP-recipe-v1 §6) against its own golden
                               path rather than a runtime flag on the
                               full-deps file.

Both zips are written with fixed per-entry timestamps and STORED
compression so re-running this generator is byte-identical (no spurious
git diffs from wall-clock timestamps or compressor nondeterminism).

Usage: python3 scripts/gen_mep_recipe_fixture.py
"""
from __future__ import annotations

import hashlib
import json
import struct
import zipfile
import zlib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
FIXTURE_DIR = ROOT / "docs" / "specs" / "golden" / "mep-recipe" / "fixture"

# Fixed per-entry zip timestamp (matches the DOS-epoch floor zipfile accepts)
# so regenerating the fixture never perturbs the committed bytes.
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)

SHA1_TARGET = "2A4E126D0286BEA0BF503C80A12352C57539F76B"
TILE_SHAPE = "3C004200B900A500B900A50042003C00"
TILE_PALETTE = "0F001A2C"

HIRES_TEXT = "\n".join([
    "<ver>107",
    "<scale>1",
    "<img>tiles.png",
    f"<tile>0,{TILE_SHAPE},{TILE_PALETTE},0,0,1,N",
    "<bgm>0,0,theme.ogg",
    "<sfx>0,1,jump.ogg",
    f"<patch>game.ips,{SHA1_TARGET}",
    "",
])
IPS_PATCH_BYTES = b"PATCH" + b"EOF-fixture-bytes"
THEME_OGG_BYTES = b"OggS\x00" + b"mep-recipe-fixture-theme-audio"
JUMP_OGG_BYTES = b"OggS\x00" + b"mep-recipe-fixture-jump-audio"


def _png_rgba(width: int = 8, height: int = 8, rgba: tuple = (200, 40, 40, 255)) -> bytes:
    """A tiny, valid 8x8 RGBA PNG -- enough to satisfy `<img>` consumers
    without pulling in an image library dependency."""
    raw = b"".join(b"\x00" + bytes(rgba) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, level=9))
        + chunk(b"IEND", b"")
    )


def _write_deterministic_zip(path: Path, files: dict) -> str:
    """Writes `files` (in insertion order) into a zip at `path` with a
    fixed timestamp and STORED compression per entry, then returns the
    sha256 hex digest of the zip file's actual bytes on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            info = zipfile.ZipInfo(filename=name, date_time=FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_recipe(primary_sha256: str, audio_sha256: str) -> dict:
    return {
        "recipe": 1,
        "sources": {
            "primary": {
                "url": "https://example.org/packs/mep-recipe-fixture-1.0.0.zip",
                "sha256": primary_sha256,
            },
            "deps": [
                {
                    "id": "audio",
                    "sha256": audio_sha256,
                    "size": len(THEME_OGG_BYTES) + len(JUMP_OGG_BYTES),
                    "hints": ["https://example.org/audio/mep-recipe-fixture-ogg.zip"],
                    "license": "CC0-1.0",
                    "user_supplied": True,
                }
            ],
        },
        "ops": [
            {"op": "copy", "from": "primary:hires.txt", "to": "hires.txt"},
            {"op": "copy", "from": "primary:tiles.png", "to": "tiles.png"},
            {"op": "copy", "from": "primary:game.ips", "to": "patches/game.ips"},
            {"op": "glob", "from": "audio:**/*.ogg", "to": "audio/"},
            {"op": "rewrite-paths", "file": "hires.txt", "tags": ["bgm", "sfx"], "prefix": "audio/"},
        ],
        "pack": {
            "mep": "1.1.0",
            "name": "MEP Recipe Fixture Pack",
            "version": "1.0.0",
            "license": "CC0-1.0",
            "targets": [{"system": "nes", "sha1": SHA1_TARGET}],
            "patches": [{"sha1": SHA1_TARGET, "file": "patches/game.ips"}],
            "sections": {"textures": {"path": ""}},
        },
        "policy": {"apply_patch_only_if_complete": True},
    }


def generate(out_dir: Path = FIXTURE_DIR) -> dict:
    """Writes primary.zip, audio-dep.zip, recipe.json and
    recipe-missing-dep.json into `out_dir`. Returns the real sha256 hex
    digests actually used, so callers (including the test) can verify
    the emitted recipe documents against them without re-parsing JSON."""
    primary_zip = out_dir / "primary.zip"
    audio_zip = out_dir / "audio-dep.zip"

    primary_sha256 = _write_deterministic_zip(primary_zip, {
        "hires.txt": HIRES_TEXT.encode("utf-8"),
        "tiles.png": _png_rgba(),
        "game.ips": IPS_PATCH_BYTES,
    })
    audio_sha256 = _write_deterministic_zip(audio_zip, {
        "theme.ogg": THEME_OGG_BYTES,
        "folder/jump.ogg": JUMP_OGG_BYTES,
    })

    recipe = _build_recipe(primary_sha256, audio_sha256)
    recipe_text = json.dumps(recipe, indent=2) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "recipe.json").write_text(recipe_text, encoding="utf-8")
    (out_dir / "recipe-missing-dep.json").write_text(recipe_text, encoding="utf-8")

    return {"primary.zip": primary_sha256, "audio-dep.zip": audio_sha256}


def main() -> int:
    hashes = generate()
    print(f"wrote fixture to {FIXTURE_DIR}")
    for name, digest in hashes.items():
        print(f"  {name} sha256 = {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
