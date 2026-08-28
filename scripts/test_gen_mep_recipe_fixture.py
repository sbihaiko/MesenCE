#!/usr/bin/env python3
"""Framework-free checks for scripts/gen_mep_recipe_fixture.py (F6.4a).

Guards against the mistake the existing format-only
docs/specs/golden/mep-recipe/recipe.json golden made: declaring a
`sha256` field equal to the hash of the empty string instead of the hash
of real, committed bytes (MEP-recipe-v1 §9). Every check here recomputes
sha256 from the actual bytes on disk / just written and compares it
against the recipe document's declared value -- never trusting the
generator's own return value alone.

Usage: python3 scripts/test_gen_mep_recipe_fixture.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
FIXTURE_DIR = ROOT / "docs" / "specs" / "golden" / "mep-recipe" / "fixture"

sys.path.insert(0, str(SCRIPTS))
import gen_mep_recipe_fixture as gen  # noqa: E402
import mep_recipe  # noqa: E402

FAILURES = []
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def _generated_fixture():
    """Yields a tempdir holding a just-generated fixture copy (the
    *_committed_* check below covers the git-committed copy)."""
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        gen.generate(tmp)
        yield tmp


def _apply_in(tmp: Path, recipe_name: str, deps: dict) -> Path:
    """Runs mep_recipe.run_recipe for `recipe_name`, returns the out dir."""
    recipe = json.loads((tmp / recipe_name).read_text(encoding="utf-8"))
    out = tmp / (recipe_name[: -len(".json")] + "-out")
    mep_recipe.run_recipe(recipe, tmp / "primary.zip", deps=deps, out=out, rom_name=None)
    return out


def check_generated_recipe_hashes_match_the_real_written_bytes():
    """AC-6: declared sha256/size fields must equal the real written bytes."""
    with _generated_fixture() as tmp:
        actual_primary = _sha256(tmp / "primary.zip")
        actual_audio = _sha256(tmp / "audio-dep.zip")
        if actual_primary == EMPTY_SHA256 or actual_audio == EMPTY_SHA256:
            fail("real fixture bytes hash to the empty-string sha256 placeholder")
            return
        actual_audio_size = (tmp / "audio-dep.zip").stat().st_size
        for name in ("recipe.json", "recipe-missing-dep.json"):
            recipe = json.loads((tmp / name).read_text(encoding="utf-8"))
            dep = recipe["sources"]["deps"][0]
            declared_primary = recipe["sources"]["primary"]["sha256"]
            if declared_primary != actual_primary:
                fail(f"{name}: declared primary sha256 {declared_primary} != real bytes hash {actual_primary}")
                return
            if dep["sha256"] != actual_audio:
                fail(f"{name}: declared audio sha256 {dep['sha256']} != real bytes hash {actual_audio}")
                return
            if dep["size"] != actual_audio_size:
                fail(f"{name}: declared dep size {dep['size']} != actual audio-dep.zip size {actual_audio_size}")
                return
            if declared_primary == EMPTY_SHA256 or dep["sha256"] == EMPTY_SHA256:
                fail(f"{name}: a declared sha256 field is the empty-string placeholder")
                return
        ok("generated recipe.json / recipe-missing-dep.json sha256/size fields match the real written bytes")


def check_generated_recipe_documents_validate():
    with _generated_fixture() as tmp:
        for name in ("recipe.json", "recipe-missing-dep.json"):
            recipe = json.loads((tmp / name).read_text(encoding="utf-8"))
            errors = mep_recipe.validate_recipe(recipe)
            if errors:
                fail(f"{name}: generated recipe failed validate_recipe: {'; '.join(errors)}")
                return
        ok("generated recipe documents pass mep_recipe.validate_recipe")


def check_committed_fixture_matches_real_bytes_on_disk():
    """The git-committed fixture (not a fresh regen) must itself hash-match."""
    if not FIXTURE_DIR.exists():
        fail(f"committed fixture directory does not exist: {FIXTURE_DIR}")
        return
    actual_primary = _sha256(FIXTURE_DIR / "primary.zip")
    actual_audio = _sha256(FIXTURE_DIR / "audio-dep.zip")
    if actual_primary == EMPTY_SHA256 or actual_audio == EMPTY_SHA256:
        fail("committed fixture zip(s) hash to the empty-string sha256 (zero-byte file?)")
        return
    for name in ("recipe.json", "recipe-missing-dep.json"):
        recipe = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
        declared_primary = recipe["sources"]["primary"]["sha256"]
        declared_audio = recipe["sources"]["deps"][0]["sha256"]
        if declared_primary != actual_primary:
            fail(f"committed {name}: declared primary sha256 {declared_primary} != on-disk hash {actual_primary}")
            return
        if declared_audio != actual_audio:
            fail(f"committed {name}: declared audio sha256 {declared_audio} != on-disk hash {actual_audio}")
            return
    ok("committed fixture's declared sha256 fields match its own on-disk zip bytes")


def check_regenerating_is_byte_identical():
    """Risk Area: re-running the generator must not perturb committed bytes."""
    with _generated_fixture() as tmp:
        for name in ("primary.zip", "audio-dep.zip", "recipe.json", "recipe-missing-dep.json"):
            committed = (FIXTURE_DIR / name).read_bytes()
            regenerated = (tmp / name).read_bytes()
            if committed != regenerated:
                fail(f"{name}: regenerating the fixture produced different bytes than the committed copy")
                return
        ok("regenerating the fixture reproduces the committed bytes exactly")


def check_apply_full_deps_renames_track_and_keeps_patch():
    """The `rename` op (§4.3) must fire: globbed Track 01.ogg -> track01.ogg."""
    with _generated_fixture() as tmp:
        out = _apply_in(tmp, "recipe.json", {"audio": tmp / "audio-dep.zip"})
        if (out / "audio" / "Track 01.ogg").exists():
            fail("apply (full deps): unrenamed audio/Track 01.ogg survived in the output tree")
            return
        if not (out / "audio" / "track01.ogg").exists():
            fail("apply (full deps): renamed audio/track01.ogg is missing from the output tree")
            return
        if not json.loads((out / "pack.json").read_text(encoding="utf-8")).get("patches"):
            fail("apply (full deps): pack.json omits patches even though every dep resolved")
            return
        ok("apply (full deps) renames audio/Track 01.ogg -> audio/track01.ogg and keeps the patch")


def check_apply_missing_dep_skips_rename_transitively():
    """§6: a missing dep must transitively skip `rename` reading its glob."""
    with _generated_fixture() as tmp:
        out = _apply_in(tmp, "recipe-missing-dep.json", {})
        if (out / "audio").exists():
            fail("apply (missing dep): audio/ was written despite the dep being withheld")
            return
        if not (out / "hires.txt").exists():
            fail("apply (missing dep): hires.txt (a surviving copy) is missing")
            return
        if json.loads((out / "pack.json").read_text(encoding="utf-8")).get("patches"):
            fail("apply (missing dep): pack.json still declares patches with a dep missing")
            return
        ok("apply (missing dep) transitively skips the rename and withholds the patch")


def check_full_and_missing_dep_recipes_are_the_same_document():
    with _generated_fixture() as tmp:
        full = (tmp / "recipe.json").read_text(encoding="utf-8")
        missing = (tmp / "recipe-missing-dep.json").read_text(encoding="utf-8")
        if full != missing:
            fail("recipe.json and recipe-missing-dep.json are not the same document")
            return
        ok("recipe.json and recipe-missing-dep.json carry the same recipe document")


def main():
    check_generated_recipe_hashes_match_the_real_written_bytes()
    check_generated_recipe_documents_validate()
    check_committed_fixture_matches_real_bytes_on_disk()
    check_regenerating_is_byte_identical()
    check_apply_full_deps_renames_track_and_keeps_patch()
    check_apply_missing_dep_skips_rename_transitively()
    check_full_and_missing_dep_recipes_are_the_same_document()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nAll gen_mep_recipe_fixture checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
