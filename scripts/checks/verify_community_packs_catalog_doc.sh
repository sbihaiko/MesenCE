#!/usr/bin/env bash
# AC-8: docs/community-packs.md exists, with the expected table header
# (link/game/console/author/category/date) and the "Most popular" section,
# ready to be overwritten by the catalog workflow.
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

check "Link" "the Link column"
check "Game" "the Game column"
check "Console" "the Console column"
check "Author" "the Author column"
check "Category" "the Category column"
check "Date" "the Date column"
check "Most popular" "the 'Most popular' section"
check "popularity proxy" "the popularity-proxy label"

if [ "$FAIL" -ne 0 ]; then
  exit 1
fi

echo "PASS: AC-8 ($DOC has the table header + Most popular section)"
