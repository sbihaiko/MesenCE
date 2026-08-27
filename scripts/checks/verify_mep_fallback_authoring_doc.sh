#!/usr/bin/env bash
# Verifies docs/hd-pack-authoring.md (AC-10): documents, for pack authors,
# the last-priority compatibility path for release zips that wrap the pack
# in a subfolder/promo folder (the MEP-v1.md §2.1 rule 9 fallback).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOC="$REPO_ROOT/docs/hd-pack-authoring.md"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$DOC" ] || fail "file not found: $DOC"

grep -qi 'wrapper\|promo' "$DOC" \
  || fail "$DOC does not mention a wrapper/promo folder in release zips"

grep -qi 'subfolder' "$DOC" \
  || fail "$DOC does not mention the subfolder search (fallback)"

grep -q 'MEP-v1.md' "$DOC" \
  || fail "$DOC does not reference MEP-v1.md"

grep -q '§2.1' "$DOC" \
  || fail "$DOC does not reference MEP-v1.md's §2.1 section (where the fallback is normative)"

grep -qi 'last-resort\|last-priority\|last priority' "$DOC" \
  || fail "$DOC does not make clear that the fallback is last-priority/last-resort"

grep -qi 'ambigu' "$DOC" \
  || fail "$DOC does not mention rejection on ambiguity (more than one candidate subfolder)"

grep -qi 'mep_lint.py' "$DOC" \
  || fail "$DOC does not mention that automatic triage (mep_lint.py) also applies the fallback"

# The recommendation remains to avoid depending on the fallback, preferring
# the first-class conventions (pack.json at the root / zip named as the ROM).
grep -qi 'pack.json at the.*root\|pack.json.*zip root' "$DOC" \
  || fail "$DOC does not recommend pack.json at the root as the preferred alternative to the fallback"

echo "PASS: docs/hd-pack-authoring.md documents the wrapper/promo compatibility path pointing to MEP-v1.md §2.1"
