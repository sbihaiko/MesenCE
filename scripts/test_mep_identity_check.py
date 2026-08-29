#!/usr/bin/env python3
"""Framework-free checks for the P.2 collision logic
(scripts/mep_identity_check.py, PRD-player-shell §3.3).

Covers `collision()` only — the pure decision (duplicate content_id / foreign
origin on an existing pack_id / none); the live `gh` reads and writes of the
CLI are runner-side and need no test here.

Usage: python3 scripts/test_mep_identity_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from mep_identity_check import collision  # noqa: E402

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def existing(content_id=None, pack_id=None, origin="u/r", issue=5):
    return {"issue_number": issue, "content_id": content_id, "pack_id": pack_id, "origin": origin}


def check_duplicate():
    ex = [existing(content_id="c" * 64, pack_id="p1"), existing(content_id=None, pack_id="p2")]
    got = collision({"content_id": "c" * 64, "pack_id": "p3", "origin": "u/r"}, ex)
    if got != ("duplicate", 5):
        fail(f"same content_id should be a duplicate of #5, got {got!r}")
        return
    ok("same content_id under any pack_id -> duplicate of the holder")


def check_origin():
    ex = [existing(content_id="c1", pack_id="pack", origin="sbihaiko/contra80s")]
    got = collision({"content_id": "zzz", "pack_id": "pack", "origin": "other/repo"}, ex)
    if got != ("origin", "sbihaiko/contra80s", 5):
        fail(f"foreign origin claiming 'pack' should be origin-bound, got {got!r}")
        return
    ok("same pack_id from a different origin -> origin collision")
    # Same origin + same pack_id is a legitimate new revision: no collision.
    got2 = collision({"content_id": "zzz", "pack_id": "pack", "origin": "sbihaiko/contra80s"}, ex)
    if got2 is not None:
        fail(f"same-origin revision must not collide, got {got2!r}")
        return
    ok("same pack_id from the SAME origin is a revision, not a collision")


def check_none():
    ex = [existing(content_id="c1", pack_id="p1", origin="u/r")]
    got = collision({"content_id": "c2", "pack_id": "p2", "origin": "u/r"}, ex)
    if got is not None:
        fail(f"a genuinely new pack must not collide, got {got!r}")
        return
    # Duplicate wins over origin when both apply (first rule).
    ex2 = [existing(content_id="dup", pack_id="pack", origin="u/r")]
    got = collision({"content_id": "dup", "pack_id": "pack", "origin": "other/repo"}, ex2)
    if got != ("duplicate", 5):
        fail(f"duplicate must take precedence over origin, got {got!r}")
        return
    ok("no collision for a new pack; duplicate rule beats origin rule")


def main():
    check_duplicate()
    check_origin()
    check_none()

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
