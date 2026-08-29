#!/usr/bin/env bash
# CLAUDE.md en-US rule (2026-08-29): developer-facing strings in source code
# (C#/C++ under Core/, UI/ and scripts/) must be English. The 2026-08-27 manual
# sweep missed two pt-BR usage strings ("uso:" in scripts/headless_record.cpp
# and scripts/roles_probe.cpp); this machine guard scans source for a string
# literal starting with "uso (pt-BR for "usage") - a pattern English never
# produces (the English word is "usage", "usa..."), so false positives are
# structurally impossible. Comment-only lines are skipped, so prose that quotes
# the old form is not flagged.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# A pt-BR usage string opens with "uso followed by ':' ' ' '.' or the closing
# quote. Skip comment-only lines (indented or not) and build/derived dirs.
hits=$(grep -rnE '"uso[ :."]' Core UI scripts \
	--include='*.cpp' --include='*.h' --include='*.cs' 2>/dev/null \
	| grep -vE '^\S+:[0-9]+:[[:space:]]*(//|/\*|\*)' \
	| grep -v '/graphify-out/' \
	| grep -v '/obj/' \
	| grep -v '/bin/' \
	|| true)

if [[ -n "$hits" ]]; then
	echo "FAIL: pt-BR usage string(s) found (CLAUDE.md en-US rule):"
	echo "$hits"
	exit 1
fi

echo "OK: no pt-BR usage strings in source (CLAUDE.md en-US)"
