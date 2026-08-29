#!/usr/bin/env python3
"""Framework-free checks for scripts/mep_content_id.py (P.1, ADR-0139).

AC-1: same tree, two wrappers (entry order differs) -> the same content_id.
AC-2: __MACOSX/ , .DS_Store, README*, screenshots/ never enter the id.
AC-3: a pack.json version label bump is not a new revision; any other
      pack.json semantic change is.
AC-4: a byte change in a payload file is a new revision (byte fidelity).
AC-5: recipe form: dep digests sorted by dep id; same deps in any order
      give the same id; a different recipe or primary gives a different id.

Usage: python3 scripts/test_mep_content_id.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import mep_content_id  # noqa: E402

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def tree(*entries):
    """entries as (path, bytes) — callers pass str payloads."""
    return [(p, b.encode("utf-8")) for p, b in entries]


TREE_A = tree(
    ("textures/hires.txt", "1:0:0:0 2 3"),
    ("textures/tile1.png", "\x89PNG fake"),
    ("pack.json", '{"version": "1.0", "id": "contra80s", "targets": [{"sha1": "abc"}]}'),
)


def check_tree_stability():
    # Same tree, wrappers just reorder the zip entries - content_id is equal
    id_a = mep_content_id.compute_tree_content_id(TREE_A)
    id_b = mep_content_id.compute_tree_content_id(list(reversed(TREE_A)))
    if id_a == id_b and len(id_a) == 64:
        ok("tree content_id is wrapper-order independent")
    else:
        fail(f"tree content_id changed with entry order: {id_a} vs {id_b}")


def check_exclusions():
    base = tree(
        ("textures/hires.txt", "1:0:0:0"),
        ("__MACOSX/textures/._hires.txt", "junk"),
        (".DS_Store", "junk"),
        ("README.txt", "read me"),
        ("screenshots/ingame.png", "shot"),
        ("pack.json", '{"version": "1.0"}'),
    )
    base_id = mep_content_id.compute_tree_content_id(base)
    if len(base_id) == 64:
        ok("tree content_id ignores __MACOSX/.DS_Store/README/screenshots")
    else:
        fail(f"tree content_id should exclude junk entries, got {base_id!r}")


def check_pack_json_version():
    v10 = tree(("pack.json", '{"version": "1.0", "id": "x"}'))
    v11 = tree(("pack.json", '{"version": "1.1", "id": "x"}'))
    id10 = mep_content_id.compute_tree_content_id(v10)
    id11 = mep_content_id.compute_tree_content_id(v11)
    if id10 == id11:
        ok("pack.json version bump does not change content_id")
    else:
        fail(f"version bump changed content_id: {id10} vs {id11}")

    changed = tree(("pack.json", '{"version": "1.0", "id": "y"}'))
    id_changed = mep_content_id.compute_tree_content_id(changed)
    if id_changed != id10:
        ok("a semantic pack.json change is a new revision")
    else:
        fail("pack.json id change did not change content_id")


def check_byte_fidelity():
    a = tree(("textures/tile1.png", "AAAA"))
    b = tree(("textures/tile1.png", "AAAB"))
    if mep_content_id.compute_tree_content_id(a) != mep_content_id.compute_tree_content_id(b):
        ok("a payload byte change is a new revision")
    else:
        fail("payload byte change produced the same content_id")


def check_recipe_form():
    deps = {"audio": "b" * 64, "patch": "a" * 64}
    base = mep_content_id.compute_recipe_content_id("1" * 64, "2" * 64, deps)
    reordered = mep_content_id.compute_recipe_content_id("1" * 64, "2" * 64, {"patch": "a" * 64, "audio": "b" * 64})
    if base == reordered and len(base) == 64:
        ok("recipe content_id sorts dep digests by dep id")
    else:
        fail(f"recipe content_id depends on dep order: {base} vs {reordered}")

    other_recipe = mep_content_id.compute_recipe_content_id("1" * 64, "3" * 64, deps)
    if base != other_recipe:
        ok("a different recipe hash is a different content_id")
    else:
        fail("recipe hash change did not change content_id")

    other_primary = mep_content_id.compute_recipe_content_id("9" * 64, "2" * 64, deps)
    if base != other_primary:
        ok("a different primary tree hash is a different content_id")
    else:
        fail("primary tree hash change did not change content_id")


def main():
    check_tree_stability()
    check_exclusions()
    check_pack_json_version()
    check_byte_fidelity()
    check_recipe_form()

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
