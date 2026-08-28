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


def check_generated_hashes_are_not_the_empty_string_placeholder():
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        hashes = gen.generate(tmp)
        for name, digest in hashes.items():
            if digest == EMPTY_SHA256:
                fail(f"{name}: generator returned the empty-string sha256 placeholder")
                return
        ok("generator's returned hashes are not the empty-string placeholder")


def check_generated_recipe_hashes_match_the_real_written_bytes():
    """AC-6: the recipe document's declared sha256 fields must equal the
    sha256 of the bytes gen_mep_recipe_fixture.py actually wrote for
    primary.zip / audio-dep.zip -- not any placeholder value."""
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        hashes = gen.generate(tmp)
        actual_primary = _sha256(tmp / "primary.zip")
        actual_audio = _sha256(tmp / "audio-dep.zip")
        if hashes["primary.zip"] != actual_primary:
            fail(f"generator's returned primary hash {hashes['primary.zip']} != actual bytes hash {actual_primary}")
            return
        if hashes["audio-dep.zip"] != actual_audio:
            fail(f"generator's returned audio hash {hashes['audio-dep.zip']} != actual bytes hash {actual_audio}")
            return
        for name in ("recipe.json", "recipe-missing-dep.json"):
            recipe = json.loads((tmp / name).read_text(encoding="utf-8"))
            declared_primary = recipe["sources"]["primary"]["sha256"]
            declared_audio = recipe["sources"]["deps"][0]["sha256"]
            if declared_primary != actual_primary:
                fail(f"{name}: declared primary sha256 {declared_primary} != real bytes hash {actual_primary}")
                return
            if declared_audio != actual_audio:
                fail(f"{name}: declared audio sha256 {declared_audio} != real bytes hash {actual_audio}")
                return
            if declared_primary == EMPTY_SHA256 or declared_audio == EMPTY_SHA256:
                fail(f"{name}: a declared sha256 field is the empty-string placeholder")
                return
        ok("generated recipe.json / recipe-missing-dep.json sha256 fields match the real written bytes")


def check_generated_recipe_documents_validate():
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        gen.generate(tmp)
        for name in ("recipe.json", "recipe-missing-dep.json"):
            recipe = json.loads((tmp / name).read_text(encoding="utf-8"))
            errors = mep_recipe.validate_recipe(recipe)
            if errors:
                fail(f"{name}: generated recipe failed validate_recipe: {'; '.join(errors)}")
                return
        ok("generated recipe documents pass mep_recipe.validate_recipe")


def check_committed_fixture_matches_real_bytes_on_disk():
    """The fixture actually committed to git (not a freshly regenerated
    copy) must itself carry real, matching hashes -- catches drift if the
    committed files and the generator's current output ever diverge."""
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
            fail(f"committed {name}: declared primary sha256 {declared_primary} != on-disk primary.zip hash {actual_primary}")
            return
        if declared_audio != actual_audio:
            fail(f"committed {name}: declared audio sha256 {declared_audio} != on-disk audio-dep.zip hash {actual_audio}")
            return
    ok("committed fixture's declared sha256 fields match its own on-disk zip bytes")


def check_regenerating_is_byte_identical():
    """Risk Area (spec): re-running the generator must not perturb the
    committed bytes -- fixed zip timestamps/compression keep it that way."""
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        gen.generate(tmp)
        for name in ("primary.zip", "audio-dep.zip", "recipe.json", "recipe-missing-dep.json"):
            committed = (FIXTURE_DIR / name).read_bytes()
            regenerated = (tmp / name).read_bytes()
            if committed != regenerated:
                fail(f"{name}: regenerating the fixture produced different bytes than the committed copy")
                return
        ok("regenerating the fixture reproduces the committed bytes exactly")


def check_full_and_missing_dep_recipes_are_the_same_document():
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        gen.generate(tmp)
        full = (tmp / "recipe.json").read_text(encoding="utf-8")
        missing = (tmp / "recipe-missing-dep.json").read_text(encoding="utf-8")
        if full != missing:
            fail("recipe.json and recipe-missing-dep.json are not the same document")
            return
        ok("recipe.json and recipe-missing-dep.json carry the same recipe document")


def main():
    check_generated_hashes_are_not_the_empty_string_placeholder()
    check_generated_recipe_hashes_match_the_real_written_bytes()
    check_generated_recipe_documents_validate()
    check_committed_fixture_matches_real_bytes_on_disk()
    check_regenerating_is_byte_identical()
    check_full_and_missing_dep_recipes_are_the_same_document()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nAll gen_mep_recipe_fixture checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
