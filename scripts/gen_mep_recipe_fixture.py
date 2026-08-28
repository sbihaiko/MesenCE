#!/usr/bin/env python3
"""Generates the real-bytes MEP-recipe-v1 golden fixture (F6.4a, F6.4c).

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
  wrapped-subfolder.zip     -- F6.4c: payload under a wrapper folder named
                               after ROM_NAME, no probe at the container
                               root (ADR-0120 name-anchored fallback)
  recipe-wrapped-subfolder.json
  nested-zip.zip            -- F6.4c: container holding exactly one root-level
                               inner-pack.zip plus a non-pack sibling
                               (ADR-0120 nested top-level zip)
  recipe-nested-zip.json
  bare-probe.zip            -- F6.4c: wrapper holding the payload plus a bare
                               legacy probe-basename marker (preset.cfg)
                               distinct from the hires.txt leaf (ADR-0121)
  recipe-bare-probe.json

All zips are written with fixed per-entry timestamps and STORED
compression so re-running this generator is byte-identical (no spurious
git diffs from wall-clock timestamps or compressor nondeterminism).

Usage: python3 scripts/gen_mep_recipe_fixture.py
"""
from __future__ import annotations

import hashlib
import io
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

# F6.4c: the single wrapper/container name shared verbatim by the generator,
# the generator test, and Bloco E -- one constant, spelled the same on both
# interpreters, because the C++ side (MepPack::FindFallbackSubfolder) is
# ROM-name-anchored and fail-closes on an empty romName (MepPack.cpp), while
# the Python side resolves the same shape structurally too.
ROM_NAME = "mep-recipe-fixture-rom"

SHA1_TARGET = "2A4E126D0286BEA0BF503C80A12352C57539F76B"
TILE_SHAPE = "3C004200B900A500B900A50042003C00"
TILE_PALETTE = "0F001A2C"

HIRES_TEXT = "\n".join([
    "<ver>107",
    "<scale>1",
    "<img>tiles.png",
    f"<tile>0,{TILE_SHAPE},{TILE_PALETTE},0,0,1,N",
    "<bgm>0,0,track01.ogg",
    "<sfx>0,1,jump.ogg",
    f"<patch>game.ips,{SHA1_TARGET}",
    "",
])
IPS_PATCH_BYTES = b"PATCH" + b"EOF-fixture-bytes"
# Named "Track 01.ogg" (space, mixed case) inside the dep zip on purpose:
# the `rename` op below normalizes it to `track01.ogg`, exercising both
# op 3 of MEP-recipe-v1 §4.3 and its §6 transitive-skip branch (this file
# is produced only by the `glob` op that reads the "audio" dep, so a
# missing dep must skip the rename too, not just the glob).
TRACK01_OGG_BYTES = b"OggS\x00" + b"mep-recipe-fixture-theme-audio"
JUMP_OGG_BYTES = b"OggS\x00" + b"mep-recipe-fixture-jump-audio"

# Static (hash-independent) recipe pieces, hoisted to module scope so
# `_build_recipe` stays a short assembly of the two hashed fields
# (max_lines_per_function guardrail).
OPS = [
    {"op": "copy", "from": "primary:hires.txt", "to": "hires.txt"},
    {"op": "copy", "from": "primary:tiles.png", "to": "tiles.png"},
    {"op": "copy", "from": "primary:game.ips", "to": "patches/game.ips"},
    {"op": "glob", "from": "audio:**/*.ogg", "to": "audio/"},
    {"op": "rename", "from": "audio/Track 01.ogg", "to": "audio/track01.ogg"},
    {"op": "rewrite-paths", "file": "hires.txt", "tags": ["bgm", "sfx"], "prefix": "audio/"},
]
PACK = {
    "mep": "1.1.0",
    "name": "MEP Recipe Fixture Pack",
    "version": "1.0.0",
    "license": "CC0-1.0",
    "targets": [{"system": "nes", "sha1": SHA1_TARGET}],
    "patches": [{"sha1": SHA1_TARGET, "file": "patches/game.ips"}],
    "sections": {"textures": {"path": ""}},
}


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


def _deterministic_zip_bytes(files: dict) -> bytes:
    """Returns deterministic zip bytes for `files` (fixed timestamps, STORED,
    0o644 per-entry, insertion order) without writing to disk -- used when a
    zip must be embedded inside another (the F6.4c nested-zip case)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in files.items():
            info = zipfile.ZipInfo(filename=name, date_time=FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    return buffer.getvalue()


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


def _pack_files_at_zip_root() -> dict:
    """The pack payload at a zip's own root -- the base primary.zip shape."""
    return {
        "hires.txt": HIRES_TEXT.encode("utf-8"),
        "tiles.png": _png_rgba(),
        "game.ips": IPS_PATCH_BYTES,
    }


def _pack_files_at_wrapper_root() -> dict:
    """The same payload laid out directly under a wrapper folder's own root
    (no textures//audio/ wrapper) -- the ADR-0120/0121 discovery shape."""
    return {
        f"{ROM_NAME}/hires.txt": HIRES_TEXT.encode("utf-8"),
        f"{ROM_NAME}/tiles.png": _png_rgba(),
        f"{ROM_NAME}/game.ips": IPS_PATCH_BYTES,
    }


# F6.4c discovery edge cases, each with its own golden recipe document. The
# three shapes are kept disjoint so both interpreters agree on the root
# (mep_lint.open_primary tries the nested zip before the fallbacks while the
# C++ DiscoverPrimaryRoot tries root hits / fallback before the nested zip).
EDGE_CASE_STEMS = ("wrapped-subfolder", "nested-zip", "bare-probe")


def _write_edge_case_primaries(out_dir: Path) -> dict:
    """Writes the three F6.4c discovery edge-case primaries into `out_dir`
    and returns {filename: sha256-hex-of-the-file's-real-bytes}."""
    hashes = {}
    for name, files in (
        # ADR-0120: a subfolder whose name anchors on the ROM name; payload
        # at the wrapper root, no probe at the container root.
        ("wrapped-subfolder.zip", _pack_files_at_wrapper_root()),
        # ADR-0120 nested top-level zip: container holds exactly one
        # root-level .zip (the real pack, at its own root) plus a non-pack
        # sibling so the 'exactly one' rule is pinned. The sha256 declared
        # for this primary is the hash of the OUTER container bytes -- that
        # is the artifact the installer receives (MepRecipeOps reads the
        # nested zip out of it).
        ("nested-zip.zip", {
            "inner-pack.zip": _deterministic_zip_bytes(_pack_files_at_zip_root()),
            "readme.txt": b"not the pack\n",
        }),
        # ADR-0121: wrapper holding the payload plus a bare legacy
        # probe-basename marker (preset.cfg) distinct from the hires.txt
        # leaf; same ROM_NAME as the wrapped-subfolder case.
        ("bare-probe.zip", {
            **_pack_files_at_wrapper_root(),
            f"{ROM_NAME}/preset.cfg": b"fixture probe marker\n",
        }),
    ):
        hashes[name] = _write_deterministic_zip(out_dir / name, files)
    return hashes


def _write_edge_case_recipes(out_dir: Path, audio_sha256: str, audio_size: int) -> None:
    """Writes recipe-<stem>.json for every F6.4c edge-case primary, each
    reusing the shared audio-dep.zip and the base OPS/PACK shape."""
    for stem in EDGE_CASE_STEMS:
        recipe = _build_recipe(_sha256_of(out_dir / f"{stem}.zip"), audio_sha256, audio_size)
        (out_dir / f"recipe-{stem}.json").write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_recipe(primary_sha256: str, audio_sha256: str, audio_size: int) -> dict:
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
                    # Size of the downloadable dep artifact itself (the zip),
                    # not the sum of its uncompressed entries -- MEP-recipe-v1
                    # §3.3 / §12 both describe `size` as the same artifact
                    # whose `sha256` is declared.
                    "size": audio_size,
                    "hints": ["https://example.org/audio/mep-recipe-fixture-ogg.zip"],
                    "license": "CC0-1.0",
                    "user_supplied": True,
                }
            ],
        },
        "ops": OPS,
        "pack": PACK,
        "policy": {"apply_patch_only_if_complete": True},
    }


def generate(out_dir: Path = FIXTURE_DIR) -> dict:
    """Writes the base fixture (primary.zip, audio-dep.zip, recipe.json,
    recipe-missing-dep.json) and the F6.4c discovery edge-case fixtures
    (wrapped-subfolder / nested-zip / bare-probe + their recipe documents)
    into `out_dir`. Returns the real sha256 hex digests actually used, so
    callers (including the test) can verify the emitted recipe documents
    against them without re-parsing JSON."""
    primary_zip = out_dir / "primary.zip"
    audio_zip = out_dir / "audio-dep.zip"

    primary_sha256 = _write_deterministic_zip(primary_zip, _pack_files_at_zip_root())
    audio_sha256 = _write_deterministic_zip(audio_zip, {
        "Track 01.ogg": TRACK01_OGG_BYTES,
        "folder/jump.ogg": JUMP_OGG_BYTES,
    })

    recipe = _build_recipe(primary_sha256, audio_sha256, audio_zip.stat().st_size)
    recipe_text = json.dumps(recipe, indent=2) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "recipe.json").write_text(recipe_text, encoding="utf-8")
    (out_dir / "recipe-missing-dep.json").write_text(recipe_text, encoding="utf-8")

    edge_hashes = _write_edge_case_primaries(out_dir)
    _write_edge_case_recipes(out_dir, audio_sha256, audio_zip.stat().st_size)

    return {"primary.zip": primary_sha256, "audio-dep.zip": audio_sha256, **edge_hashes}


def main() -> int:
    hashes = generate()
    print(f"wrote fixture to {FIXTURE_DIR}")
    for name, digest in hashes.items():
        print(f"  {name} sha256 = {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
