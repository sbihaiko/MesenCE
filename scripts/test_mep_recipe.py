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


def check_missing_dep_rename_skipped():
    """Regression for the recipe-gate false-reject found in review: the
    ADR-0138 §1 reference recipe chains `glob` (from a dep) then `rename`
    on a path inside that glob's output. When the dep is missing (exactly
    what the CI recipe-gate's --dep-less dry-run produces for every
    declared dep, ADR §16), the `rename` op must be skipped like the
    `glob` that would have fed it, not raise `RecipeError`.
    """
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        recipe_path, primary, _audio, recipe = _make_split(tmp)
        rename_op = {"op": "rename", "from": "audio/theme.ogg", "to": "audio/track01.ogg"}
        glob_index = next(i for i, op in enumerate(recipe["ops"]) if op["op"] == "glob")
        recipe["ops"].insert(glob_index + 1, rename_op)
        recipe_path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
        out = tmp / "out"
        try:
            mep_recipe.run_recipe(recipe, primary, deps={}, out=out, rom_name=None)
        except mep_recipe.RecipeError as exc:
            fail(f"rename on a missing-dep glob output raised instead of being skipped: {exc}")
            return
        if (out / "audio").exists() and any((out / "audio").iterdir()):
            fail("missing-dep audio/ should stay empty when its glob is skipped")
            return
        if not (out / "pack.json").exists():
            fail("missing-dep-plus-rename dry-run did not write pack.json")
            return
        ok("rename referencing a missing-dep glob output is skipped, not a hard error")


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


PACK_URL = "https://github.com/example/repo/releases/download/v1/pack.zip"
PACK_SHA256 = hashlib.sha256(b"synthetic-primary-artifact").hexdigest()
AUDIO_URL = "https://example.com/audio/synthetic-split-ogg.zip"
AUDIO_SHA256 = hashlib.sha256(b"synthetic-audio-artifact").hexdigest()

ISSUE_BODY_NO_ASSETS = "\n".join([
    "### Pack link",
    "",
    PACK_URL,
    "",
    "### External assets (optional)",
    "",
    "_No response_",
    "",
    "### External assets license (optional)",
    "",
    "_No response_",
    "",
])


def _issue_body_with_assets(line: str) -> str:
    return "\n".join([
        "### Pack link",
        "",
        PACK_URL,
        "",
        "### External assets (optional)",
        "",
        line,
        "",
        "### External assets license (optional)",
        "",
        "CC0-1.0",
        "",
    ])


def _classify_fragment() -> dict:
    return {
        "ops": [
            {"op": "copy", "from": "primary:hires.txt", "to": "hires.txt"},
            {"op": "glob", "from": "audio:**/*.ogg", "to": "audio/"},
        ],
        "deps": [
            {
                "id": "audio",
                "hints": [AUDIO_URL],
                "license": "CC0-1.0",
                "user_supplied": True,
            }
        ],
        "pack": {
            "name": "Synthetic Split Pack",
            "version": "1.0.0",
            "targets": [{"system": "nes", "sha1": SHA1}],
        },
    }


def check_assemble_absent_no_assets_no_fragment():
    status, recipe = mep_recipe.assemble_sources(ISSUE_BODY_NO_ASSETS, None, PACK_URL, PACK_SHA256)
    if status != "absent" or recipe is not None:
        fail(f"expected absent/None, got {status!r}/{recipe!r}")
        return
    status2, recipe2 = mep_recipe.assemble_sources(ISSUE_BODY_NO_ASSETS, {}, PACK_URL, PACK_SHA256)
    if status2 != "absent" or recipe2 is not None:
        fail(f"expected absent/None for empty classify fragment, got {status2!r}/{recipe2!r}")
        return
    ok("no external_assets text + no classify fragment -> absent, nothing written")


def check_assemble_present_merges_classify():
    line = f"{AUDIO_URL} {AUDIO_SHA256} 1048576"
    body = _issue_body_with_assets(line)
    classify = _classify_fragment()
    status, recipe = mep_recipe.assemble_sources(body, classify, PACK_URL, PACK_SHA256)
    if status != "present" or recipe is None:
        fail(f"expected present recipe, got {status!r}/{recipe!r}")
        return
    if recipe["sources"]["primary"] != {"url": PACK_URL, "sha256": PACK_SHA256}:
        fail(f"sources.primary not from CI hash/pack url: {recipe['sources']['primary']!r}")
        return
    deps = recipe["sources"]["deps"]
    if len(deps) != 1 or deps[0]["sha256"] != AUDIO_SHA256 or deps[0]["size"] != 1048576:
        fail(f"sources.deps not populated with parsed sha256/size: {deps!r}")
        return
    if deps[0]["hints"] != [AUDIO_URL] or deps[0]["license"] != "CC0-1.0" or deps[0]["user_supplied"] is not True:
        fail(f"sources.deps did not merge classify's id/hints/license/user_supplied: {deps!r}")
        return
    if recipe["ops"] != classify["ops"] or recipe["pack"] != classify["pack"]:
        fail("assembled recipe did not pass through classify's ops/pack verbatim")
        return
    if recipe["recipe"] != mep_recipe.RECIPE_VERSION:
        fail(f"assembled recipe missing/wrong 'recipe' version: {recipe.get('recipe')!r}")
        return
    ok("well-formed external_assets line -> present, sources merged with classify's ops/deps/pack")


def check_assemble_absent_when_classify_fragment_is_empty():
    """A well-formed external_assets line with classify emitting the
    schema-required keys but all empty (`{"ops": [], "deps": [], "pack":
    {}}`, the shape a non-split pack gets once the schema requires the
    keys) must still be 'absent', not a schema-clean-looking 'present'
    that validate_recipe would then reject (ADR-0138 §2/§7/§10)."""
    line = f"{AUDIO_URL} {AUDIO_SHA256} 1048576"
    body = _issue_body_with_assets(line)
    status, recipe = mep_recipe.assemble_sources(body, {"ops": [], "deps": [], "pack": {}}, PACK_URL, PACK_SHA256)
    if status != "absent" or recipe is not None:
        fail(f"empty-but-present classify fragment should be absent, got {status!r}/{recipe!r}")
        return
    ok("classify ops/deps/pack all empty -> absent even with a declared external asset")


def check_assemble_present_keeps_unmatched_line_as_dep():
    """classify's `deps` can be shorter than the declared external_assets
    lines (or empty outright) — every line must still surface as a dep;
    ADR-0138 §12 makes the lines themselves the authoritative dependency
    list, so a line with no matching classify dep must never be silently
    dropped from `sources.deps`."""
    line = f"{AUDIO_URL} {AUDIO_SHA256} 1048576"
    body = _issue_body_with_assets(line)
    classify = {
        "ops": [{"op": "copy", "from": "primary:hires.txt", "to": "hires.txt"}],
        "deps": [],
        "pack": {"name": "Synthetic Split Pack", "version": "1.0.0", "targets": [{"system": "nes", "sha1": SHA1}]},
    }
    status, recipe = mep_recipe.assemble_sources(body, classify, PACK_URL, PACK_SHA256)
    if status != "present" or recipe is None:
        fail(f"unmatched line with real classify content should be present, got {status!r}/{recipe!r}")
        return
    deps = recipe["sources"]["deps"]
    if len(deps) != 1:
        fail(f"declared external asset line was dropped from sources.deps: {deps!r}")
        return
    if deps[0]["sha256"] != AUDIO_SHA256 or deps[0]["size"] != 1048576 or deps[0]["hints"] != [AUDIO_URL]:
        fail(f"synthesized dep missing the line's own sha256/size/hints: {deps[0]!r}")
        return
    errors = mep_recipe.validate_recipe(recipe)
    if errors:
        fail(f"recipe with a synthesized dep failed validate_recipe: {errors}")
        return
    ok("external_assets line with no matching classify dep still becomes sources.deps entry")


def check_assemble_present_matches_hint_despite_trailing_slash():
    """A hints URL differing from the declared line only by a trailing
    slash must still match — a purely cosmetic difference must not flip
    a real dependency into 'refused'."""
    line = f"{AUDIO_URL} {AUDIO_SHA256} 1048576"
    body = _issue_body_with_assets(line)
    classify = _classify_fragment()
    classify["deps"][0]["hints"] = [AUDIO_URL + "/"]
    status, recipe = mep_recipe.assemble_sources(body, classify, PACK_URL, PACK_SHA256)
    if status != "present" or recipe is None:
        fail(f"trailing-slash hint mismatch should still match, got {status!r}/{recipe!r}")
        return
    deps = recipe["sources"]["deps"]
    if len(deps) != 1 or deps[0]["id"] != "audio" or deps[0]["sha256"] != AUDIO_SHA256:
        fail(f"trailing-slash hint did not merge classify's dep metadata: {deps!r}")
        return
    ok("hints URL differing only by a trailing slash still matches its external_assets line")


def check_assemble_present_drops_classify_size_when_line_has_none():
    """A classify-supplied `size` on a matched dep must never survive a
    size-less external_assets line — sha256/size are the deterministic
    step's alone to set (ADR-0138 §4/§11: submitter-declared, never
    classify's), so a fabricated LLM size must not leak into the
    assembled recipe just because the line omitted the optional field."""
    line = AUDIO_URL + " " + AUDIO_SHA256  # no size field on the line
    body = _issue_body_with_assets(line)
    classify = _classify_fragment()
    classify["deps"][0]["size"] = 999
    status, recipe = mep_recipe.assemble_sources(body, classify, PACK_URL, PACK_SHA256)
    if status != "present" or recipe is None:
        fail(f"expected present recipe, got {status!r}/{recipe!r}")
        return
    deps = recipe["sources"]["deps"]
    if len(deps) != 1 or "size" in deps[0]:
        fail(f"classify-supplied size leaked into a size-less line's dep: {deps!r}")
        return
    if deps[0]["sha256"] != AUDIO_SHA256:
        fail(f"sha256 not overwritten from the parsed line: {deps!r}")
        return
    ok("classify-supplied dep size does not survive a size-less external_assets line")


def check_assemble_refused_missing_sha256():
    body = _issue_body_with_assets(AUDIO_URL)
    status, recipe = mep_recipe.assemble_sources(body, _classify_fragment(), PACK_URL, PACK_SHA256)
    if status != "refused" or recipe is not None:
        fail(f"dep line missing sha256 should refuse, got {status!r}/{recipe!r}")
        return
    ok("external_assets line missing sha256 -> refused, no partial recipe")


def check_assemble_refused_malformed_line():
    bad_url = _issue_body_with_assets(f"not-a-url {AUDIO_SHA256} 1048576")
    status, recipe = mep_recipe.assemble_sources(bad_url, _classify_fragment(), PACK_URL, PACK_SHA256)
    if status != "refused" or recipe is not None:
        fail(f"non-HTTPS url should refuse, got {status!r}/{recipe!r}")
        return
    bad_sha = _issue_body_with_assets(f"{AUDIO_URL} not-hex-and-too-short 1048576")
    status2, recipe2 = mep_recipe.assemble_sources(bad_sha, _classify_fragment(), PACK_URL, PACK_SHA256)
    if status2 != "refused" or recipe2 is not None:
        fail(f"malformed sha256 should refuse, got {status2!r}/{recipe2!r}")
        return
    ok("malformed url/sha256 line is rejected as refused, not silently accepted")


def check_assemble_sources_cli_roundtrip():
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        line = f"{AUDIO_URL} {AUDIO_SHA256} 1048576"
        body_path = tmp / "issue-body.md"
        body_path.write_text(_issue_body_with_assets(line), encoding="utf-8")
        classify_path = tmp / "classify.json"
        classify_path.write_text(json.dumps(_classify_fragment()), encoding="utf-8")
        out_path = tmp / "mep_recipe.json"
        rc = mep_recipe.main([
            "mep_recipe.py", "assemble-sources",
            "--issue-body", str(body_path),
            "--classify", str(classify_path),
            "--pack-url", PACK_URL,
            "--pack-sha256", PACK_SHA256,
            "--out", str(out_path),
        ])
        if rc != 0:
            fail(f"assemble-sources CLI exited {rc}")
            return
        if not out_path.exists():
            fail("assemble-sources CLI did not write --out on a present recipe")
            return
        written = json.loads(out_path.read_text(encoding="utf-8"))
        errors = mep_recipe.validate_recipe(written)
        if errors:
            fail(f"CLI-assembled recipe failed validate_recipe: {errors}")
            return
        ok("assemble-sources CLI writes a validate_recipe-clean document")


def check_assemble_sources_cli_absent_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        body_path = tmp / "issue-body.md"
        body_path.write_text(ISSUE_BODY_NO_ASSETS, encoding="utf-8")
        out_path = tmp / "mep_recipe.json"
        rc = mep_recipe.main([
            "mep_recipe.py", "assemble-sources",
            "--issue-body", str(body_path),
            "--pack-url", PACK_URL,
            "--pack-sha256", PACK_SHA256,
            "--out", str(out_path),
        ])
        if rc != 0:
            fail(f"assemble-sources CLI exited {rc} for the absent case")
            return
        if out_path.exists():
            fail("assemble-sources CLI wrote --out for an absent recipe")
            return
        ok("assemble-sources CLI writes nothing when recipe_status is absent")


def main():
    check_golden_validates()
    check_unknown_op_rejected()
    check_escaping_path_rejected()
    check_dry_run_lint_clean()
    check_wrapped_primary_uses_lint_discovery()
    check_incomplete_withholds_patch()
    check_missing_dep_rename_skipped()
    check_hash_mismatch_aborts()
    check_assemble_absent_no_assets_no_fragment()
    check_assemble_absent_when_classify_fragment_is_empty()
    check_assemble_present_merges_classify()
    check_assemble_present_keeps_unmatched_line_as_dep()
    check_assemble_present_matches_hint_despite_trailing_slash()
    check_assemble_present_drops_classify_size_when_line_has_none()
    check_assemble_refused_missing_sha256()
    check_assemble_refused_malformed_line()
    check_assemble_sources_cli_roundtrip()
    check_assemble_sources_cli_absent_writes_nothing()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nAll mep_recipe checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
