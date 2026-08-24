#!/usr/bin/env bash
# ADR-0007: fail when Core/*.cpp on disk and Core.vcxproj <ClCompile> entries drift.
# The makefile globs (find Core -name '*.cpp') while Core.vcxproj enumerates by hand,
# so a source added on macOS/Linux builds green while the MSVC project silently rots.
set -euo pipefail
cd "$(dirname "$0")/.."

tmp_disk=$(mktemp)
tmp_proj=$(mktemp)
trap 'rm -f "$tmp_disk" "$tmp_proj"' EXIT

(cd Core && find . -name '*.cpp' | sed -e 's|^\./||' -e 's|/|\\|g' | sort) > "$tmp_disk"
sed -n 's/.*<ClCompile Include="\([^"]*\)".*/\1/p' Core/Core.vcxproj | sort > "$tmp_proj"

if ! diff "$tmp_proj" "$tmp_disk" > /dev/null; then
	echo "ERROR: Core source manifest drift (ADR-0007)." >&2
	echo "Entries only in Core.vcxproj (<) vs only on disk (>):" >&2
	diff "$tmp_proj" "$tmp_disk" | grep -E '^[<>]' >&2
	echo "Fix: add/remove the matching <ClCompile>/<ClInclude> entries in Core/Core.vcxproj." >&2
	exit 1
fi

echo "OK: Core.vcxproj matches Core/*.cpp on disk ($(wc -l < "$tmp_disk" | tr -d ' ') files)."
