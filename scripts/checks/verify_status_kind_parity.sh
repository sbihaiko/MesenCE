#!/usr/bin/env bash
# AC-6 (F6.3b, ADR-0138 §29): the two Status-literal -> kind pairs
# ("Aceito (MEP completo)" -> "mep", "Aceito parcial (HD Mesen)" ->
# "hd-legacy") are defined exactly once across scripts/ -- inside
# mei_rules.STATUS_TO_KIND -- and mei_catalog_entry.py imports that
# mapping instead of hardcoding a second, independent copy of the
# pairing. Fails loudly (names the offending file/count), never
# vacuously: deleting STATUS_TO_KIND, or adding a second hardcoded pair
# anywhere in scripts/, both fail this check. No mocks: reads the real
# source files from disk.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS_DIR="$REPO_ROOT/scripts"
RULES_FILE="$SCRIPTS_DIR/mei_rules.py"
ENTRY_FILE="$SCRIPTS_DIR/mei_catalog_entry.py"

STATUS_MEP='"Aceito (MEP completo)"'
STATUS_HD='"Aceito parcial (HD Mesen)"'
KIND_MEP='"mep"'
KIND_HD='"hd-legacy"'

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -d "$SCRIPTS_DIR" ] || fail "scripts/ directory not found: $SCRIPTS_DIR"
[ -f "$RULES_FILE" ] || fail "mei_rules.py not found: $RULES_FILE"
[ -f "$ENTRY_FILE" ] || fail "mei_catalog_entry.py not found: $ENTRY_FILE"

# lines under scripts/*.py containing BOTH literals (the pairing form),
# across the whole tree -- never vacuously empty when the pairing exists.
count_pair() {
  local status_literal="$1" kind_literal="$2"
  grep -rn -F --include='*.py' -- "$status_literal" "$SCRIPTS_DIR" 2>/dev/null \
    | grep -F -- "$kind_literal" || true
}

# assert_single_pair <label> <status-literal> <kind-literal>: fails loudly
# unless the pairing is found exactly once, and only in mei_rules.py.
assert_single_pair() {
  local label="$1" status_literal="$2" kind_literal="$3"
  local matches count
  matches="$(count_pair "$status_literal" "$kind_literal")"
  if [ -z "$matches" ]; then
    fail "$label pairing ($status_literal -> $kind_literal) not found anywhere in scripts/ -- expected exactly one definition, in mei_rules.STATUS_TO_KIND"
  fi
  count="$(printf '%s\n' "$matches" | grep -c .)"
  if [ "$count" -ne 1 ]; then
    fail "$label pairing ($status_literal -> $kind_literal) defined $count time(s) in scripts/, expected exactly 1:
$matches"
  fi
  if ! printf '%s\n' "$matches" | grep -qF "$RULES_FILE"; then
    fail "$label pairing ($status_literal -> $kind_literal) is defined outside mei_rules.py: $matches"
  fi
  echo "OK: $label pairing ($status_literal -> $kind_literal) defined exactly once, in $(basename "$RULES_FILE")"
}

assert_single_pair "mep" "$STATUS_MEP" "$KIND_MEP"
assert_single_pair "hd-legacy" "$STATUS_HD" "$KIND_HD"

# mei_catalog_entry.py must import the mapping, never restate it.
grep -qE '^(import mei_rules|from mei_rules import)' "$ENTRY_FILE" \
  || fail "mei_catalog_entry.py does not import mei_rules"
grep -q 'STATUS_TO_KIND' "$ENTRY_FILE" \
  || fail "mei_catalog_entry.py imports mei_rules but never references STATUS_TO_KIND"
if grep -F -- "$STATUS_MEP" "$ENTRY_FILE" | grep -qF -- "$KIND_MEP"; then
  fail "mei_catalog_entry.py hardcodes the mep pairing instead of importing mei_rules.STATUS_TO_KIND"
fi
if grep -F -- "$STATUS_HD" "$ENTRY_FILE" | grep -qF -- "$KIND_HD"; then
  fail "mei_catalog_entry.py hardcodes the hd-legacy pairing instead of importing mei_rules.STATUS_TO_KIND"
fi

echo "PASS: Status->kind pairing defined exactly once (mei_rules.STATUS_TO_KIND); mei_catalog_entry.py imports it, does not restate it"
