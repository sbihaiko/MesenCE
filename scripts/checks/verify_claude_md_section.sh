#!/usr/bin/env bash
# AC-10: CLAUDE.md keeps its bug-tracking section intact and carries a
# separate Community HD/MEP Pack triage section after it. No mocks: this
# reads the real CLAUDE.md from the repo root.
#
# History: AC-10 originally asserted the pre-translation pt-BR section
# ("Rastreamento de bugs (GitHub Project)") stayed byte-for-byte a file
# prefix. CLAUDE.md has since been translated to en-US (CLAUDE.md language
# rule) and gained the ADR section before the bug section, so a byte-for-byte
# prefix check is no longer the right shape. This rewrite keeps the AC-10
# intent — bug-tracking section present and un-duplicated, pack-triage
# section present after it — against the current en-US headings.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLAUDE_MD="$REPO_ROOT/CLAUDE.md"

BUG_HEADING="## Bug tracking (GitHub Project)"
PACK_HEADING="## Community HD/MEP Pack triage (GitHub Project)"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[[ -f "$CLAUDE_MD" ]] || fail "CLAUDE.md not found at $CLAUDE_MD"

# Exactly one occurrence of each heading: no duplication of either section.
bug_count=$(grep -Fc "$BUG_HEADING" "$CLAUDE_MD")
[[ "$bug_count" -eq 1 ]] || fail "expected 1 occurrence of '$BUG_HEADING', found $bug_count"

pack_count=$(grep -Fc "$PACK_HEADING" "$CLAUDE_MD")
[[ "$pack_count" -eq 1 ]] || fail "expected 1 occurrence of '$PACK_HEADING', found $pack_count"

# The pack-triage section must come strictly after the bug section (the two
# flows are separate; the pack section references the bug section as
# "a separate flow from the bug tracking above").
bug_line=$(grep -Fn "$BUG_HEADING" "$CLAUDE_MD" | cut -d: -f1)
pack_line=$(grep -Fn "$PACK_HEADING" "$CLAUDE_MD" | cut -d: -f1)
[[ "$pack_line" -gt "$bug_line" ]] \
  || fail "'$PACK_HEADING' must appear after '$BUG_HEADING' (bug line $bug_line, pack line $pack_line)"

# The bug section's key content markers must be present (the section was not
# gutted): board name, report-bug.sh helper, and the Status/Priority fields.
grep -Fq "MesenCE Bug Tracker" "$CLAUDE_MD" || fail "bug section missing 'MesenCE Bug Tracker' board reference"
grep -Fq "scripts/report-bug.sh" "$CLAUDE_MD" || fail "bug section missing the scripts/report-bug.sh helper reference"
grep -Fq "To triage" "$CLAUDE_MD" || fail "bug section missing the Status 'To triage' field reference"

# The pack-triage section must reference the separate board (Project 3).
grep -Fq "MesenCE Community Packs" "$CLAUDE_MD" || fail "pack-triage section missing 'MesenCE Community Packs' board reference"

echo "PASS: CLAUDE.md keeps the bug-tracking section intact and contains the pack-triage section after it"
