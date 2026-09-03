#!/usr/bin/env bash
# AC-8: docs/adr/0120-*.md states the provenance of the
# TasticHacks/Contra80s zip-structure claim (citing issue #3 and/or the
# release source it was described from), explicitly distinguishes what was
# independently verified by reading the current source (PrepareZip /
# DetectConventionLayout require an exact root layout with no recursion)
# from what was not independently re-verified (the real published zip's
# byte-for-byte structure), and qualifies any "would not load today" claim
# by that coverage gap instead of presenting it as an exhaustively confirmed
# fact. No mocks: reads the real ADR file from disk.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADR_GLOB=("$REPO_ROOT"/docs/adr/0120-*.md)

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -e "${ADR_GLOB[0]}" ] || fail "no docs/adr/0120-*.md file found"
[ "${#ADR_GLOB[@]}" -eq 1 ] || fail "expected exactly 1 file matching 0120-*.md, found ${#ADR_GLOB[@]}: ${ADR_GLOB[*]}"

ADR="${ADR_GLOB[0]}"

require_i() {
  # require_i <description> <ERE pattern>  — case-insensitive extended regex
  local desc="$1" pattern="$2"
  grep -qiE "$pattern" "$ADR" || fail "$desc: pattern '$pattern' not found in $ADR"
}

require_f() {
  # require_f <description> <fixed string>
  local desc="$1" pattern="$2"
  grep -qF "$pattern" "$ADR" || fail "$desc: string '$pattern' not found in $ADR"
}

# --- Provenance of the motivating claim ------------------------------------
require_i "mentions TasticHacks" "TasticHacks"
require_i "mentions Contra80s" "Contra80s"
require_i "cites issue #3 and/or the release source" "issue #?3|issues/3"
grep -qiE "github\\.com/TasticHacks/Contra80s|releases/download" "$ADR" \
  || fail "does not cite the pack's release source (GitHub Releases URL)"

# --- Independently verified vs. not independently re-verified --------------
require_i "marks something as independently verified" \
  "independently verified"
require_i "marks something as NOT re-verified" \
  "not.*(independently )?(re-)?verified|not.*independently.*re-inspected|was not independently"

# The specific fact that WAS verified: PrepareZip / DetectConventionLayout
# require an exact root layout with no recursion.
require_f "mentions PrepareZip" "PrepareZip"
require_f "mentions DetectConventionLayout" "DetectConventionLayout"
require_i "states 'no recursion' for the current behavior" "no recursion"
require_i "cites MepPackManager.cpp as the source" "MepPackManager\\.cpp"
require_i "cites MepPack.cpp as the source" "MepPack\\.cpp"

# The specific fact that was NOT independently re-verified: the real
# published zip's byte-for-byte structure.
grep -qiE "byte-for-byte|actual (internal )?structure|real.*zip.*structure" "$ADR" \
  || fail "does not mention the real zip's byte-for-byte structure as not re-verified"

# --- The "would not load today" claim must be qualified, not asserted flat -
if grep -qiE "would not load (today|as-is)" "$ADR"; then
  grep -qiE "qualif|coverage gap|gap\\)|described.*not independently|not.*independently re-inspected" "$ADR" \
    || fail "the 'would not load today' claim appears without an explicit qualification for the verification gap"
fi

echo "PASS: $ADR cites the TasticHacks/Contra80s provenance (issue #3 / release), distinguishes what was verified directly against the current code (PrepareZip/DetectConventionLayout with no recursion) from what was not re-verified (the real zip's byte-for-byte structure), and qualifies any claim that the pack 'would not load today' by that gap"
