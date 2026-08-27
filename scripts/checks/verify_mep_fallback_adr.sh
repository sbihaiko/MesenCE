#!/usr/bin/env bash
# AC-7: .dev-squad/adr/0120-*.md documents the zip subfolder fallback as:
#   (a) an additive, lowest-priority extension of ADR-0040/ADR-0049's
#       discovery precedence (not a reordering of it);
#   (b) a pure, I/O-free function that PrepareZip consults, with
#       PrepareZip's outFolder contract held fixed (no signature change);
#   (c) the C++ (name match) vs C#/Python (structural match) asymmetry,
#       together with its named follow-up (an optional ROM-name parameter);
#   (d) the standalone C++ E2E zip-pipeline test harness explicitly
#       deferred as a separate, not-this-task follow-up.
# No mocks: reads the real ADR file from disk.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADR_GLOB=("$REPO_ROOT"/.dev-squad/adr/0120-*.md)

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -e "${ADR_GLOB[0]}" ] || fail "no .dev-squad/adr/0120-*.md file found"
[ "${#ADR_GLOB[@]}" -eq 1 ] || fail "expected exactly 1 file matching 0120-*.md, found ${#ADR_GLOB[@]}: ${ADR_GLOB[*]}"

ADR="${ADR_GLOB[0]}"

MIN_LINES=40
LINE_COUNT="$(wc -l < "$ADR" | tr -d ' ')"
[ "$LINE_COUNT" -ge "$MIN_LINES" ] || fail "$ADR has only $LINE_COUNT lines (expected >= $MIN_LINES; looks trivial)"

# Flattened (newlines -> spaces) copy for multi-word phrase checks that may
# legitimately wrap across source lines in the prose.
FLAT="$(tr '\n' ' ' < "$ADR")"

require() {
  # require <description> <pattern...>  — every pattern must be found
  # (fixed-string, case-sensitive) somewhere in the ADR.
  local desc="$1"; shift
  local pattern
  for pattern in "$@"; do
    grep -qF "$pattern" "$ADR" || fail "$desc: did not find '$pattern' in $ADR"
  done
}

# (a) additive, lowest-priority extension of ADR-0040/ADR-0049 precedence
require "references ADR-0040" "ADR-0040"
require "references ADR-0049" "ADR-0049"
grep -qiE "additive|last-priority|lowest-priority|fourth" "$ADR" \
  || fail "does not describe the rule as a last-priority addition (additive/last-priority)"
grep -qiE "precedence" "$ADR" || fail "does not mention the precedence chain"
echo "$FLAT" | grep -qiE "without reordering|never reorder|not reordered|unchanged.*precedence|precedence.*unchanged" \
  || fail "does not explicitly state that the existing precedence is NOT reordered"

# (b) pure, I/O-free function; PrepareZip's outFolder contract held fixed
require "mentions PrepareZip" "PrepareZip"
grep -qiE "pure|I/O-free|no I/O|I\\O-free" "$ADR" \
  || fail "does not describe the function as pure/I/O-free"
grep -qF "outFolder" "$ADR" || fail "does not mention outFolder"
grep -qiE "contract.*(fixed|unchanged)|signature.*(fixed|unchanged|stays exactly)|held fixed" "$ADR" \
  || fail "does not state that PrepareZip's contract/signature stays unchanged"

# (c) C++ (name) vs C#/Python (structural) asymmetry + named follow-up
grep -qiE "asymmetry" "$ADR" || fail "does not name the C++ vs C#/Python asymmetry"
require "mentions MepZipValidator" "MepZipValidator"
require "mentions mep_lint.py" "mep_lint.py"
grep -qiE "name match|by name|name-based" "$ADR" || fail "does not describe the C++ side as name-based matching"
grep -qiE "structural|structure match" "$ADR" || fail "does not describe the C#/Python side as structural matching"
grep -qiE "ROM-name parameter|ROM name parameter|optional.*ROM.*name" "$ADR" \
  || fail "does not name the optional ROM-name-parameter follow-up"
grep -qiE "follow-up|follow up" "$ADR" || fail "does not mark the item as a named follow-up"

# (d) standalone C++ E2E zip-pipeline harness deferred as separate follow-up
grep -qiE "E2E|end-to-end" "$ADR" || fail "does not mention the E2E harness"
grep -qiE "deferred|separate.*follow-up|not-this-task" "$ADR" \
  || fail "does not mark the E2E harness as deferred/out of scope for this task"
grep -qiE "ZipReader" "$ADR" || fail "does not link the deferred harness to ZipReader/miniz"

echo "PASS: $ADR documents (a) the additive last-priority extension over ADR-0040/ADR-0049, (b) a pure, I/O-free function with PrepareZip's outFolder contract held fixed, (c) the C++ (name) vs C#/Python (structural) asymmetry with its named follow-up, and (d) the deferred C++ E2E harness"
