#!/usr/bin/env python3
"""Framework-free checks for nested-zip game discovery (repo-link spike,
ADR-0143). Given a container shaped like a GitHub repo archive — a wrapper
folder holding subfolders that each contain a game zip rather than an
extracted pack — discover_game_roots must enumerate the nested game zips as
one root per game, so a single repo link can split into N packs + N sibling
issues. Also verifies the fail-closed edges: unrelated zips (docs, bonus,
HTML) and non-pack zips do not count, a single nested zip does not split,
and a container that already resolves by subfolder keeps its behavior.

Usage: python3 scripts/test_mep_nested_zip.py
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import mep_lint  # noqa: E402

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def make_zip(entries: dict) -> bytes:
    """A synthetic zip from {inner_path: bytes}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in entries.items():
            z.writestr(path, data)
    return buf.getvalue()


HIRES_AUDIO = b"<ver>105\n<bgm>0,1,Stage 1.ogg\n"
HIRES_TEX = b"<ver>105\n<img>0,0,Chr_00_0.png\n"


def check_repo_like():
    """AC-1 (the spike): a repo-like container enumerates its nested game zips
    as one root per game, ignoring the wrapper and unrelated content. A
    subfolder holding several valid game zips (Duck_Hunt's Audio/NEA/HDV1.1
    variants) still yields ONE root — one game, one slot, one issue."""
    game_zips = {
        "HDnes-main/1942/1942audio.zip": make_zip({"hires.txt": HIRES_AUDIO}),
        "HDnes-main/Dr_Mario/NEA-DrMario_v2.zip": make_zip({"hires.txt": HIRES_AUDIO}),
        # Duck_Hunt carries three valid zips; all must collapse to one root.
        "HDnes-main/Duck_Hunt/DuckHunt-Audio.zip": make_zip({"hires.txt": HIRES_AUDIO}),
        "HDnes-main/Duck_Hunt/DuckHunt-NEA.zip": make_zip({"hires.txt": HIRES_AUDIO}),
        "HDnes-main/Duck_Hunt/DuckHuntHDV1.1.zip": make_zip({"hires.txt": HIRES_TEX}),
        "HDnes-main/Ice_Climber/HDpack-IceClimber(USA,Europe).zip": make_zip({"hires.txt": HIRES_TEX}),
        "HDnes-main/Super_Mario_Bros-2/NEA-smb2.zip": make_zip({"hires.txt": HIRES_AUDIO}),
        "HDnes-main/Yie_Ar_Kung_Fu/NEA-Yie.Ar.Kung-Fu.zip": make_zip({"hires.txt": HIRES_AUDIO}),
    }
    entries = dict(game_zips)
    entries["HDnes-main/HTML/FILES/HDNes-Graphics-Pac-master.zip"] = make_zip({"README.md": b"hi"})
    entries["HDnes-main/README.md"] = b"# HDnes\n"
    entries["HDnes-main/index.html"] = b"<html></html>\n"
    src = mep_lint.Source.from_zip_bytes(make_zip(entries), label="repo.zip")
    roots = mep_lint.discover_game_roots(src, "UNKNOWN")
    expected = [
        ("HDnes-main/1942", "1942"),
        ("HDnes-main/Dr_Mario", "Dr_Mario"),
        ("HDnes-main/Duck_Hunt", "Duck_Hunt"),
        ("HDnes-main/Ice_Climber", "Ice_Climber"),
        ("HDnes-main/Super_Mario_Bros-2", "Super_Mario_Bros-2"),
        ("HDnes-main/Yie_Ar_Kung_Fu", "Yie_Ar_Kung_Fu"),
    ]
    # Exact list: six roots, no duplicates (Duck_Hunt's 3 zips collapse to 1).
    if len(roots) != len(expected):
        fail(f"repo-like roots: got {len(roots)} entries {sorted(roots)!r}, expected {len(expected)}")
        return
    for i, (exp_prefix, exp_game) in enumerate(expected):
        prefix, game = roots[i]
        if prefix != exp_prefix:
            fail(f"repo-like roots[{i}]: prefix {prefix!r}, expected {exp_prefix!r}")
            return
        if game != exp_game:
            fail(f"repo-like roots[{i}] ({prefix}): game {game!r}, expected {exp_game!r}")
            return
    ok("repo-like container enumerates 6 nested game zips, one root per game (multi-zip subfolder collapses)")


def check_unrelated_zips_excluded():
    """AC-2: a nested zip that is not a pack root (no hires.txt/pack.json at
    its own root) is not a game candidate — a docs/bonus zip must not create
    a spurious slot."""
    entries = {
        "HDnes-main/1942/1942audio.zip": make_zip({"hires.txt": HIRES_AUDIO}),
        "HDnes-main/docs/bonus.zip": make_zip({"README.md": b"not a pack"}),
    }
    src = mep_lint.Source.from_zip_bytes(make_zip(entries), label="mix.zip")
    roots = mep_lint.discover_game_roots(src, "UNKNOWN")
    if dict(roots) != {"HDnes-main/1942": "1942"}:
        fail(f"unrelated nested zip should not count: {roots!r}")
        return
    ok("a nested zip without an internal pack root is not a game candidate")


def check_pack_json_nested():
    """AC-3: a nested zip whose pack.json names a target is detected, and the
    game name comes from targets[0].name (ADR-0143), not the zip basename."""
    pack_json = b'{"version":"1.0.0","targets":[{"name":"Dr. Mario","system":"nes"}]}'
    entries = {
        "HDnes-main/Dr_Mario/NEA-DrMario_v2.zip": make_zip({"pack.json": pack_json}),
    }
    src = mep_lint.Source.from_zip_bytes(make_zip(entries), label="pm.zip")
    roots = mep_lint.discover_game_roots(src, "UNKNOWN")
    if dict(roots) != {"HDnes-main/Dr_Mario": "Dr. Mario"}:
        fail(f"pack.json nested root: got {roots!r}")
        return
    ok("a nested zip with pack.json is detected, named from targets[0].name")


def check_single_nested_zip_not_split():
    """AC-4: a single nested game zip is a single root (the existing one-issue
    flow) — the pipeline splits only N>1."""
    entries = {
        "HDnes-main/1942/1942audio.zip": make_zip({"hires.txt": HIRES_AUDIO}),
    }
    src = mep_lint.Source.from_zip_bytes(make_zip(entries), label="single.zip")
    roots = mep_lint.discover_game_roots(src, "UNKNOWN")
    if len(roots) != 1 or dict(roots) != {"HDnes-main/1942": "1942"}:
        fail(f"single nested zip should be one root, got {roots!r}")
        return
    ok("a single nested game zip stays a single root (no split)")


def check_subfolder_behavior_unchanged():
    """AC-5: a container that already resolves by direct subfolder candidates
    (extracted packs) keeps enumerating those — nested-zip scanning is only a
    last resort after the direct paths found nothing."""
    entries = {
        "1942/hires.txt": HIRES_AUDIO,
        "Dr_Mario/hires.txt": HIRES_AUDIO,
    }
    src = mep_lint.Source.from_zip_bytes(make_zip(entries), label="extracted.zip")
    roots = mep_lint.discover_game_roots(src, "UNKNOWN")
    if dict(roots) != {"1942": "1942", "Dr_Mario": "Dr_Mario"}:
        fail(f"direct subfolder discovery must be unchanged: {roots!r}")
        return
    ok("direct subfolder candidates still win (nested scanning is last-resort)")


def main():
    check_repo_like()
    check_unrelated_zips_excluded()
    check_pack_json_nested()
    check_single_nested_zip_not_split()
    check_subfolder_behavior_unchanged()

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
