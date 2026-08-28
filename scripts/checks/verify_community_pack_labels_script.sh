#!/usr/bin/env bash
# Verifies scripts/ensure_community_pack_labels.sh (AC-2): the LABELS array
# declares the assets:external content-index label (ADR-0138 §12/§6, additive
# — never a third verdict state) and the full 12-entry label set is intact.
# Per ADR-0035, a deliverable enumerating N items needs a count-based check,
# not one representative grep for the new entry alone.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/ensure_community_pack_labels.sh"

EXPECTED_COUNT=12
EXPECTED_NAMES=(
  community-pack pack:valid pack:invalid assets:textures assets:audio
  patch:ips patch:bps console:nes console:gb console:gbc console:sms
  assets:external
)

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$SCRIPT" ] || fail "file not found: $SCRIPT"

# Extract the "name|color|description" entries of the LABELS=( ... ) array
# literally, so the check counts real entries instead of trusting a single
# grep to represent the whole set.
ENTRIES="$(sed -n '/^LABELS=(/,/^)/p' "$SCRIPT" | grep -oE '"[^"]+\|[0-9A-Fa-f]{6}\|[^"]*"')"
[ -n "$ENTRIES" ] || fail "$SCRIPT has no LABELS array entries matching the name|color|description format"

ENTRY_COUNT="$(printf '%s\n' "$ENTRIES" | grep -c .)"
if [ "$ENTRY_COUNT" -ne "$EXPECTED_COUNT" ]; then
  fail "LABELS array has $ENTRY_COUNT entries, expected exactly $EXPECTED_COUNT"
fi

NAMES="$(printf '%s\n' "$ENTRIES" | sed -E 's/^"([^|]+)\|.*/\1/')"
UNIQUE_NAME_COUNT="$(printf '%s\n' "$NAMES" | sort -u | grep -c .)"
if [ "$UNIQUE_NAME_COUNT" -ne "$EXPECTED_COUNT" ]; then
  fail "LABELS array has $UNIQUE_NAME_COUNT unique names, expected $EXPECTED_COUNT (duplicate/typo'd label name?)"
fi

for expected in "${EXPECTED_NAMES[@]}"; do
  printf '%s\n' "$NAMES" | grep -qxF "$expected" || fail "LABELS array is missing expected label: $expected"
done

printf '%s\n' "$ENTRIES" | grep -qF '"assets:external|' || \
  fail "LABELS array is missing the assets:external content-index entry"

echo "PASS: scripts/ensure_community_pack_labels.sh LABELS array has all $EXPECTED_COUNT expected entries, including assets:external"
