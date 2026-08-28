#!/usr/bin/env bash
# AC-8: docs/community-packs.md exists, with the expected table header
# (game/console/author/date/👍) and the community-vote note, ready to
# be overwritten by the catalog workflow. The separate "Most popular"
# section this once required was folded into the 👍-ordered table itself.
set -euo pipefail

DOC="docs/community-packs.md"
FAIL=0

if [ ! -f "$DOC" ]; then
  echo "FAIL: $DOC does not exist" >&2
  exit 1
fi

check() {
  local pattern="$1"
  local label="$2"
  if ! grep -qiF "$pattern" "$DOC"; then
    echo "FAIL: $DOC does not contain $label" >&2
    FAIL=1
  fi
}

check "Game" "the Game column"
check "Console" "the Console column"
check "Author" "the Author column"
check "Date" "the Date column"
check "👍" "the 👍 column"
check "community 👍 votes" "the community-vote framing"
check "usage telemetry" "the no-telemetry statement"

if [ "$FAIL" -ne 0 ]; then
  exit 1
fi

echo "PASS: AC-8 ($DOC has the table header + community-vote note)"
