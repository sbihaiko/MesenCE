#!/usr/bin/env bash
# Verifies docs/specs/MEP-v1.md (AC-9): §2.1 documents the subfolder
# fallback as the last-priority rule of the convention chain, and the text
# names the engine-vs-validators asymmetry (name matching in the C++ engine
# vs. structural matching in MepZipValidator.cs/mep_lint.py).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOC="$REPO_ROOT/docs/specs/MEP-v1.md"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$DOC" ] || fail "file not found: $DOC"

# Isolates the text of section 2.1 (between the "### 2.1" heading and the
# next "## 3").
SECTION_2_1="$(awk '/^### 2\.1 /{flag=1} /^## 3\. /{flag=0} flag' "$DOC")"
[ -n "$SECTION_2_1" ] || fail "could not find section ### 2.1 in $DOC"

echo "$SECTION_2_1" | grep -qi 'fallback' \
  || fail "§2.1 does not mention 'fallback' (subfolder rule missing)"

echo "$SECTION_2_1" | grep -qi 'last-priority\|last priority' \
  || fail "§2.1 does not explicitly state that the fallback is the last-priority rule"

# The fallback rule must come after rule 7 (the sibling folder / legacy HD
# Pack / central containers precedence chain), not before it.
PRECEDENCE_LINE="$(grep -n 'Precedence between origins' "$DOC" | head -1 | cut -d: -f1)"
FALLBACK_LINE="$(grep -ni 'fallback' "$DOC" | head -1 | cut -d: -f1)"
[ -n "$PRECEDENCE_LINE" ] || fail "could not find rule 7 (the precedence chain) in $DOC"
[ -n "$FALLBACK_LINE" ] || fail "could not find the fallback line in $DOC"
if [ "$FALLBACK_LINE" -le "$PRECEDENCE_LINE" ]; then
  fail "the fallback (line $FALLBACK_LINE) must come AFTER the precedence chain (line $PRECEDENCE_LINE), not before it"
fi

# Names the engine (name) vs. validators (structural) asymmetry.
echo "$SECTION_2_1" | grep -qi 'asymmetry' \
  || fail "§2.1 does not use the term 'asymmetry' for the engine-vs-validators divergence"

echo "$SECTION_2_1" | grep -q 'PrepareZip' \
  || fail "§2.1 does not reference PrepareZip (the C++ engine) in the asymmetry explanation"

echo "$SECTION_2_1" | grep -q 'MepZipValidator.cs' \
  || fail "§2.1 does not reference MepZipValidator.cs (C# validator) in the asymmetry explanation"

echo "$SECTION_2_1" | grep -q 'mep_lint.py' \
  || fail "§2.1 does not reference mep_lint.py (Python validator) in the asymmetry explanation"

echo "$SECTION_2_1" | grep -qi 'name.*match' \
  || fail "§2.1 does not describe the engine's criterion (name matching)"

echo "$SECTION_2_1" | grep -qi 'structural' \
  || fail "§2.1 does not describe the validators' criterion (structural matching)"

echo "$SECTION_2_1" | grep -q 'ADR-0120' \
  || fail "§2.1 does not reference ADR-0120, which documents the full decision"

echo "PASS: docs/specs/MEP-v1.md §2.1 documents the fallback as the last-priority rule and names the engine-vs-validators asymmetry (name vs structural)"
