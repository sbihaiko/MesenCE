#!/usr/bin/env bash
# Verifies docs/hd-pack-authoring.md (AC-9, AC-3): exists, is not trivial,
# cites docs/specs/MEP-v1.md (the §5.1/§5.2/§5.3/§6 sections used in
# community-pack triage verdicts), and documents the split-distribution
# MEP Recipe flow (ADR-0138 §12): external_assets/external_assets_license,
# the assets:external label, and docs/specs/MEP-recipe-v1.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOC="$REPO_ROOT/docs/hd-pack-authoring.md"

MIN_LINES=20

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$DOC" ] || fail "file not found: $DOC"

LINE_COUNT="$(wc -l < "$DOC" | tr -d ' ')"
if [ "$LINE_COUNT" -lt "$MIN_LINES" ]; then
  fail "$DOC has only $LINE_COUNT lines (expected >= $MIN_LINES; looks trivial)"
fi

grep -q 'MEP-v1.md' "$DOC" || fail "$DOC does not reference MEP-v1.md"

for section in '§5.1' '§5.2' '§5.3' '§6'; do
  grep -qF "$section" "$DOC" || fail "$DOC does not reference section $section of MEP-v1.md"
done

grep -q '^## Split-distribution packs (MEP Recipe)' "$DOC" \
  || fail "$DOC is missing the 'Split-distribution packs (MEP Recipe)' section"

grep -qF 'MEP-recipe-v1.md' "$DOC" || fail "$DOC does not reference MEP-recipe-v1.md"

for term in 'external_assets' 'assets:external'; do
  grep -qF "$term" "$DOC" || fail "$DOC does not mention required term: $term"
done

echo "PASS: docs/hd-pack-authoring.md exists, is not trivial, references MEP-v1.md §5.1/§5.2/§5.3/§6, and documents split-distribution packs (MEP-recipe-v1.md, external_assets, assets:external)"
