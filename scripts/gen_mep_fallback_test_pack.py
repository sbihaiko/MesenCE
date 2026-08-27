#!/usr/bin/env python3
"""Generates synthetic zips to exercise the ADR-0120 structural fallback
(scripts/mep_lint.py's find_fallback_subfolder / scripts/checks/
verify_mep_fallback_lint_fixture.sh).

Neither zip has a pack.json at its root nor a filename matching the ROM's —
the two existing conventions (ADR-0040/ADR-0049) already fail by
construction, so only the fallback (or its ambiguous rejection) decides the
outcome:

  accept     <out>/mep-fallback-accept.zip   a single wrapper (real release
             zip format, "Contra80s-v1.1/Contra (U) [!]/") containing the
             full convention (textures/hires.txt, synth/preset.cfg) plus a
             loose promo file alongside it ("Contra80s-v1.1/README.txt")
             that must not confuse the search — a single candidate, must be
             accepted.
  reject     <out>/mep-fallback-reject.zip   two distinct subdirectories
             ("PackA/", "PackB/"), each with its own full convention — two
             structurally valid candidates, ambiguous, must be rejected (no
             section found).
  malformed  <out>/mep-fallback-malformed-manifest.zip   same single wrapper
             as "accept", but with an invalid pack.json (broken JSON) inside
             the discovered subdirectory — pack.json is one of the
             FALLBACK_SUFFIXES (acceptance marker), so this proves that the
             fallback lints the discovered manifest in full instead of just
             using its presence as a structural signal (see the security fix
             in mep_lint.py's history, T3's revision cycle): must be
             rejected.
  empty-path <out>/mep-fallback-empty-section-path.zip   same single
             wrapper, valid pack.json with sections.textures.path == ""
             (hires.txt at the discovered subdirectory's root, not under
             "textures/") + a broken hires.txt (<img> referencing a missing
             PNG). Regression: an empty root_prefix + path("") used to
             produce a double slash when building "<rel>/hires.txt", the
             hires.txt was never found, and the pack was accepted without
             that layer ever having been validated — must be rejected.
  root-hires <out>/mep-fallback-root-hires.zip   single wrapper without a
             pack.json, with synth/preset.cfg (valid) + a broken hires.txt
             at the discovered subdirectory's root ("legacy HD pack" layout,
             <img> referencing a missing PNG) — same regression as the item
             above, but without a manifest: the branch that recognizes a
             loose hires.txt at the container root was not mirrored under
             the fallback prefix, so the textures layer stayed mute; must be
             rejected.
  traversal  <out>/mep-fallback-traversal.zip   entries with a ".." segment
             ("../evil/textures/hires.txt", "../evil/synth/preset.cfg") —
             zip-slip-shaped, no pack.json at the root nor a filename
             matching the ROM's, so only the fallback decides. Security
             regression: find_fallback_subfolder must refuse (via safe_rel)
             this candidate instead of discovering it as the pack root —
             must be rejected with "no section found", same as the 'reject'
             fixture.
  loose-legacy <out>/mep-fallback-loose-legacy.zip   ADR-0121: a classic
             Mesen HD pack (hires.txt loose at a wrapper folder's own root,
             no textures/ wrapper at all) whose wrapper is named after a
             release/repo, not the ROM/game — the real shape of a raw
             GitHub `/archive/refs/heads/<branch>.zip` download (see
             community-pack issues #46 PepCodes/HDNes-Graphics-Pac and #47
             ModernRetroDesign/ZII-mesen). No ROM name is passed to
             mep_lint.py in this CI fixture (mirrors mep_lint.py's own
             CLI usage when the Issue Form's rom_name argument is absent),
             so only the structural (name-agnostic) fallback's new bare-
             basename acceptance can discover it — must be accepted.
  loose-legacy-ambiguous <out>/mep-fallback-loose-legacy-ambiguous.zip   two
             distinct wrapper folders, each with its own loose root
             hires.txt — two structurally valid bare-basename candidates,
             ambiguous, must be rejected (no section found), same
             fail-closed philosophy as 'reject'.

Usage:
  python3 scripts/gen_mep_fallback_test_pack.py <out-dir> [kinds...]
  (no kinds: generates accept and reject)
"""
import sys
import zipfile
from pathlib import Path

HIRES_TXT = "<ver>106\n<scale>1\n"
BROKEN_HIRES_TXT = "<ver>106\n<scale>1\n<img>missing.png\n"
PRESET_CFG = "[Studio]\nCompThreshold=0.5\n"
VALID_PACK_JSON = (
    '{"mep":"1.0.0","name":"Contra80s","version":"1.0.0","license":"MIT",'
    '"targets":[{"system":"nes","sha1":"' + "a" * 40 + '"}],'
    '"sections":{"textures":{"path":""}}}'
)

# Typical GitHub release zip format: "<Repo>-<tag>/<Game>/..."
ACCEPT_WRAPPER = "Contra80s-v1.1/Contra (U) [!]"


def _write_zip(path: Path, entries):
    if path.exists():
        path.unlink()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, text in entries:
            z.writestr(rel, text)


def write_accept_zip(path: Path):
    """A single structural candidate: accepted by the fallback (depth 4, at
    the FALLBACK_MAX_DEPTH/kMepFallbackMaxDepth/FallbackMaxDepth limit)."""
    _write_zip(path, [
        (f"{ACCEPT_WRAPPER}/textures/hires.txt", HIRES_TXT),
        (f"{ACCEPT_WRAPPER}/synth/preset.cfg", PRESET_CFG),
        ("Contra80s-v1.1/README.txt", "release wrapper promo text, not a pack layer\n"),
    ])


def write_reject_zip(path: Path):
    """Two distinct, structurally valid candidates: ambiguous, the fallback
    must refuse (return 'nothing found') instead of guessing."""
    _write_zip(path, [
        ("PackA/textures/hires.txt", HIRES_TXT),
        ("PackA/synth/preset.cfg", PRESET_CFG),
        ("PackB/textures/hires.txt", HIRES_TXT),
        ("PackB/synth/preset.cfg", PRESET_CFG),
    ])


def write_malformed_manifest_zip(path: Path):
    """Same single wrapper as accept, but with an invalid pack.json inside
    the discovered subdirectory: proves that the fallback lints the
    discovered manifest (not just using its presence as a structural
    signal)."""
    _write_zip(path, [
        (f"{ACCEPT_WRAPPER}/pack.json", "{ this is not valid json"),
        (f"{ACCEPT_WRAPPER}/textures/hires.txt", HIRES_TXT),
    ])


def write_empty_section_path_zip(path: Path):
    """Single wrapper, valid pack.json with sections.textures.path == "" and
    a broken hires.txt at the discovered subdirectory's root: proves that a
    non-empty root_prefix + path("") does not leave the textures layer
    mute."""
    _write_zip(path, [
        (f"{ACCEPT_WRAPPER}/pack.json", VALID_PACK_JSON),
        (f"{ACCEPT_WRAPPER}/hires.txt", BROKEN_HIRES_TXT),
    ])


def write_root_hires_zip(path: Path):
    """Single wrapper without a pack.json: valid synth/preset.cfg (the only
    marker that makes the subdirectory a candidate) + a broken hires.txt
    loose at the discovered subdirectory's root (legacy HD pack layout):
    proves that the hires.txt-at-root branch is mirrored under the fallback
    prefix."""
    _write_zip(path, [
        (f"{ACCEPT_WRAPPER}/synth/preset.cfg", PRESET_CFG),
        (f"{ACCEPT_WRAPPER}/hires.txt", BROKEN_HIRES_TXT),
    ])


def write_traversal_zip(path: Path):
    """Zip-slip-shaped entries ('..' segment): find_fallback_subfolder must
    refuse this candidate via safe_rel instead of discovering it as the
    pack's root (T3's revision cycle — see the security fix in mep_lint.py's
    history)."""
    _write_zip(path, [
        ("../evil/textures/hires.txt", HIRES_TXT),
        ("../evil/synth/preset.cfg", PRESET_CFG),
    ])


# GitHub-archive-style wrapper: "<Repo>-<branch>/..." — named after the repo,
# never the ROM, so no ROM-name anchor can ever match it (ADR-0121).
LOOSE_LEGACY_WRAPPER = "HDNes-Graphics-Pac-master"


def write_loose_legacy_zip(path: Path):
    """A single wrapper folder named after a repo (not the ROM), holding
    nothing but a loose hires.txt at its own root — no textures/ wrapper, no
    pack.json. The real shape of issues #46/#47's raw GitHub archive
    downloads. Only ADR-0121's bare-basename structural fallback can find
    this; must be accepted."""
    _write_zip(path, [
        (f"{LOOSE_LEGACY_WRAPPER}/hires.txt", HIRES_TXT),
        (f"{LOOSE_LEGACY_WRAPPER}/Chr_00_0.png", "not really a png, unchecked by discovery"),
    ])


def write_loose_legacy_ambiguous_zip(path: Path):
    """Two distinct repo-named wrappers, each with its own loose root
    hires.txt: two structurally valid bare-basename candidates, ambiguous,
    must be rejected rather than guessed at."""
    _write_zip(path, [
        ("RepoA-main/hires.txt", HIRES_TXT),
        ("RepoB-master/hires.txt", HIRES_TXT),
    ])


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    out = Path(sys.argv[1])
    kinds = sys.argv[2:] or ["accept", "reject"]
    out.mkdir(parents=True, exist_ok=True)

    for kind in kinds:
        if kind == "accept":
            write_accept_zip(out / "mep-fallback-accept.zip")
        elif kind == "reject":
            write_reject_zip(out / "mep-fallback-reject.zip")
        elif kind == "malformed":
            write_malformed_manifest_zip(out / "mep-fallback-malformed-manifest.zip")
        elif kind == "empty-path":
            write_empty_section_path_zip(out / "mep-fallback-empty-section-path.zip")
        elif kind == "root-hires":
            write_root_hires_zip(out / "mep-fallback-root-hires.zip")
        elif kind == "traversal":
            write_traversal_zip(out / "mep-fallback-traversal.zip")
        else:
            print(f"unknown kind: {kind}")
            return 1
        print(f"generated: {kind}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
