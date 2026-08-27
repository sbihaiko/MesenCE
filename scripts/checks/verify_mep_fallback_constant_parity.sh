#!/usr/bin/env bash
# AC-6: the ADR-0120 structural-fallback search limits (max depth 4, max
# entries 2000) are present, named, and numerically identical across the
# C++, C#, and Python sources:
#   C++    Core/Shared/EnhancementPacks/MepPack.h  kMepFallbackMaxDepth / kMepFallbackMaxEntries
#   C#     UI/Logic/MepZipValidator.cs             FallbackMaxDepth / FallbackMaxEntries
#   Python scripts/mep_lint.py                     FALLBACK_MAX_DEPTH / FALLBACK_MAX_ENTRIES
# Fails loudly (non-empty diagnostic naming the offending language), never
# vacuously, when a constant is missing or unparseable in any of the three,
# and asserts the literal values 4/2000 directly in addition to cross-
# language equality — so a divergence in ANY single source is caught, not
# just a divergence between two sources that happen to still agree with
# each other. No mocks: reads the real source files from disk.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CPP_FILE="$REPO_ROOT/Core/Shared/EnhancementPacks/MepPack.h"
CS_FILE="$REPO_ROOT/UI/Logic/MepZipValidator.cs"
PY_FILE="$REPO_ROOT/scripts/mep_lint.py"

EXPECTED_DEPTH=4
EXPECTED_ENTRIES=2000

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$CPP_FILE" ] || fail "C++: arquivo não encontrado: $CPP_FILE"
[ -f "$CS_FILE" ] || fail "C#: arquivo não encontrado: $CS_FILE"
[ -f "$PY_FILE" ] || fail "Python: arquivo não encontrado: $PY_FILE"

# extract_int <language> <file> <name-regex> <literal-name-for-errors>
# Greps for `<name> ... = <digits>` (any C++/C#/Python declaration/assignment
# style: constexpr int, private const int, or a bare module constant) and
# echoes the first match's integer value. Fails loudly, naming the language,
# when the name is absent or its value cannot be parsed as digits.
extract_int() {
  local lang="$1" file="$2" name_regex="$3" literal_name="$4"
  local line value
  line="$(grep -m1 -E "${name_regex}[[:space:]]*=[[:space:]]*[0-9]+" "$file" || true)"
  if [ -z "$line" ]; then
    fail "$lang: constante '$literal_name' não encontrada (ou sem valor numérico) em $file"
  fi
  value="$(grep -oE '=[[:space:]]*[0-9]+' <<<"$line" | head -n1 | grep -oE '[0-9]+')"
  if [ -z "$value" ]; then
    fail "$lang: constante '$literal_name' encontrada mas não deu para parsear um inteiro em $file: $line"
  fi
  echo "$value"
}

CPP_DEPTH="$(extract_int "C++" "$CPP_FILE" 'kMepFallbackMaxDepth' 'kMepFallbackMaxDepth')"
CPP_ENTRIES="$(extract_int "C++" "$CPP_FILE" 'kMepFallbackMaxEntries' 'kMepFallbackMaxEntries')"
CS_DEPTH="$(extract_int "C#" "$CS_FILE" 'FallbackMaxDepth' 'FallbackMaxDepth')"
CS_ENTRIES="$(extract_int "C#" "$CS_FILE" 'FallbackMaxEntries' 'FallbackMaxEntries')"
PY_DEPTH="$(extract_int "Python" "$PY_FILE" 'FALLBACK_MAX_DEPTH' 'FALLBACK_MAX_DEPTH')"
PY_ENTRIES="$(extract_int "Python" "$PY_FILE" 'FALLBACK_MAX_ENTRIES' 'FALLBACK_MAX_ENTRIES')"

echo "C++    kMepFallbackMaxDepth=$CPP_DEPTH kMepFallbackMaxEntries=$CPP_ENTRIES"
echo "C#     FallbackMaxDepth=$CS_DEPTH FallbackMaxEntries=$CS_ENTRIES"
echo "Python FALLBACK_MAX_DEPTH=$PY_DEPTH FALLBACK_MAX_ENTRIES=$PY_ENTRIES"

# Literal-value assertions (independent of cross-language equality: a bug
# that shifts all three sources to the same WRONG number must still fail).
[ "$CPP_DEPTH" -eq "$EXPECTED_DEPTH" ] || fail "C++: kMepFallbackMaxDepth=$CPP_DEPTH, esperado $EXPECTED_DEPTH"
[ "$CPP_ENTRIES" -eq "$EXPECTED_ENTRIES" ] || fail "C++: kMepFallbackMaxEntries=$CPP_ENTRIES, esperado $EXPECTED_ENTRIES"
[ "$CS_DEPTH" -eq "$EXPECTED_DEPTH" ] || fail "C#: FallbackMaxDepth=$CS_DEPTH, esperado $EXPECTED_DEPTH"
[ "$CS_ENTRIES" -eq "$EXPECTED_ENTRIES" ] || fail "C#: FallbackMaxEntries=$CS_ENTRIES, esperado $EXPECTED_ENTRIES"
[ "$PY_DEPTH" -eq "$EXPECTED_DEPTH" ] || fail "Python: FALLBACK_MAX_DEPTH=$PY_DEPTH, esperado $EXPECTED_DEPTH"
[ "$PY_ENTRIES" -eq "$EXPECTED_ENTRIES" ] || fail "Python: FALLBACK_MAX_ENTRIES=$PY_ENTRIES, esperado $EXPECTED_ENTRIES"

# Three-way cross-language equality (on top of the literal check above, in
# case EXPECTED_* itself ever drifts from what all three sources agree on).
if [ "$CPP_DEPTH" -ne "$CS_DEPTH" ] || [ "$CS_DEPTH" -ne "$PY_DEPTH" ]; then
  fail "max-depth diverge entre linguagens: C++=$CPP_DEPTH C#=$CS_DEPTH Python=$PY_DEPTH"
fi
if [ "$CPP_ENTRIES" -ne "$CS_ENTRIES" ] || [ "$CS_ENTRIES" -ne "$PY_ENTRIES" ]; then
  fail "max-entries diverge entre linguagens: C++=$CPP_ENTRIES C#=$CS_ENTRIES Python=$PY_ENTRIES"
fi

echo "PASS: kMepFallbackMaxDepth/FallbackMaxDepth/FALLBACK_MAX_DEPTH=$EXPECTED_DEPTH e kMepFallbackMaxEntries/FallbackMaxEntries/FALLBACK_MAX_ENTRIES=$EXPECTED_ENTRIES em C++, C# e Python"
