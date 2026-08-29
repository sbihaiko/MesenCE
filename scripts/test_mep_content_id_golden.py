#!/usr/bin/env python3
"""Parity runner for the P.1 `content_id` golden (ADR-0139).

Reads `docs/specs/golden/mep-content-id.json` and recomputes every fixture id
with the normative hasher (`scripts/mep_content_id.py`). The Core implements
the same function (MepPackManager for local containers, MepRecipeInstaller at
install time) and the unit tests check it against the same fixtures, so the
two implementations are kept honest against one shared reference.

Usage: python3 scripts/test_mep_content_id_golden.py
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import mep_content_id  # noqa: E402

GOLDEN = (
    Path(__file__).resolve().parent.parent
    / "docs" / "specs" / "golden" / "mep-content-id.json"
)

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def decode(entry) -> bytes:
    """Entry payload back to bytes. The golden keeps binary entries base64 so
    the file stays a text fixture."""
    data = entry["data"]
    if entry.get("encoding") == "base64":
        return base64.b64decode(data)
    return data.encode("utf-8")


def check_tree_fixture(fx):
    # Deliberately do NOT sort here: the golden stores a shuffled order to
    # prove wrapper-order independence is the hasher's job.
    entries = [(e["path"], decode(e)) for e in fx["entries"]]
    got = mep_content_id.compute_tree_content_id(entries)
    if got == fx["expected_content_id"]:
        ok(f"tree fixture '{fx['name']}' matches golden ({got[:12]}...)")
    else:
        fail(f"tree fixture '{fx['name']}': golden {fx['expected_content_id']} != recomputed {got}")


def check_recipe_fixture(fx):
    got = mep_content_id.compute_recipe_content_id(
        fx["primary_tree_hash"], fx["recipe_hash"], fx["deps"]
    )
    if got == fx["expected_content_id"]:
        ok(f"recipe fixture '{fx['name']}' matches golden ({got[:12]}...)")
    else:
        fail(f"recipe fixture '{fx['name']}': golden {fx['expected_content_id']} != recomputed {got}")


def main():
    data = json.loads(GOLDEN.read_text("utf-8"))
    for fx in data["fixtures"]:
        if fx["kind"] == "tree":
            check_tree_fixture(fx)
        elif fx["kind"] == "recipe":
            check_recipe_fixture(fx)
        else:
            fail(f"unknown fixture kind {fx['kind']!r} in '{fx['name']}'")

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
