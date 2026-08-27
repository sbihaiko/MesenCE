#!/usr/bin/env bash
# Regression for GitHub issue #20: scripts/mep_lint.py's
# find_fallback_subfolder_by_name (ADR-0120 §3's named follow-up) anchors a
# submitter-typed rom_name against a pack's internal subfolder name via
# exact-lowercase match or normalize_rom_core_name (region/flag-tag
# stripping) — neither used to bridge an underscore-vs-space mismatch, so a
# repo that names its per-game subfolder with underscores (e.g. HDnes's
# "Super_Mario_Bros/") never anchored against a submitter's human-typed
# "Super Mario Bros". normalize_rom_core_name must now also fold
# underscores/hyphens to spaces and collapse repeated whitespace before
# comparing. No mocks: imports and calls the real mep_lint.py functions.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${PYTHON:-python3}"

"$PY" - "$REPO_ROOT" <<'EOF'
import sys

repo_root = sys.argv[1]
sys.path.insert(0, f"{repo_root}/scripts")
from mep_lint import find_fallback_subfolder_by_name, normalize_rom_core_name  # noqa: E402


def fail(message):
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


# 1. normalize_rom_core_name folds underscores/hyphens to spaces and
#    collapses repeated whitespace, on top of its pre-existing tag-stripping
#    and lowercasing.
cases = [
    ("Super_Mario_Bros", "Super Mario Bros"),
    ("Ice_Climber_(VS)", "Ice Climber (VS System)"),
    ("Urban-Champion", "Urban Champion"),
]
for folder_name, submitted_name in cases:
    a, b = normalize_rom_core_name(folder_name), normalize_rom_core_name(submitted_name)
    if a != b:
        fail(f"normalize_rom_core_name({folder_name!r})={a!r} != normalize_rom_core_name({submitted_name!r})={b!r}")

# 2. find_fallback_subfolder_by_name anchors an underscore-named subfolder
#    (HDnes-shaped repro from issue #20) against a space-typed submitter name.
names = {
    "Super_Mario_Bros/textures/hires.txt",
    "Super_Mario_Bros/pack.json",
    "README.md",
}
result = find_fallback_subfolder_by_name(names, "Super Mario Bros")
if result is None:
    fail("find_fallback_subfolder_by_name did not anchor 'Super Mario Bros' against 'Super_Mario_Bros/'")
prefix, _depth = result
if prefix != "Super_Mario_Bros":
    fail(f"find_fallback_subfolder_by_name returned unexpected prefix {prefix!r}")

# 3. Still fails closed on genuine ambiguity: two distinct underscore-named
#    candidates both normalizing to the same submitted name.
ambiguous_names = {
    "Super_Mario_Bros/hires.txt",
    "Super-Mario-Bros/hires.txt",
}
if find_fallback_subfolder_by_name(ambiguous_names, "Super Mario Bros") is not None:
    fail("find_fallback_subfolder_by_name should fail closed on two distinct underscore/hyphen-named candidates")

print("PASS: normalize_rom_core_name folds underscores/hyphens to spaces; find_fallback_subfolder_by_name anchors HDnes-shaped underscore subfolders and still fails closed on ambiguity")
EOF
