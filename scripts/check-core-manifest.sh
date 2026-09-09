#!/usr/bin/env bash
# ADR-0007: fail when *.cpp on disk and the MSBuild project's <ClCompile> entries
# drift. The makefile globs (find <dir> -name '*.cpp') while each .vcxproj
# enumerates by hand, so a source added on macOS/Linux builds green while the
# MSVC project silently rots - and the Windows CI job fails at link time with an
# LNK2001 on symbols nobody touched.
#
# Both directories the makefile globs for C++ are covered: Core (the original
# ADR-0007 scope) and Utilities, added after Utilities/LiveRecordFormat.cpp shipped
# unlisted and broke the Windows build for four pushes. SevenZip/ and Lua/ are C
# and vendored, so they are out of scope.
set -euo pipefail
cd "$(dirname "$0")/.."

status=0

check_dir() {
	local dir="$1" proj="$2"
	local tmp_disk tmp_proj
	tmp_disk=$(mktemp)
	tmp_proj=$(mktemp)

	(cd "$dir" && find . -name '*.cpp' | sed -e 's|^\./||' -e 's|/|\\|g' | sort) > "$tmp_disk"
	sed -n 's/.*<ClCompile Include="\([^"]*\)".*/\1/p' "$proj" | grep -v '\.c$' | sort > "$tmp_proj"

	if ! diff "$tmp_proj" "$tmp_disk" > /dev/null; then
		echo "ERROR: $dir source manifest drift (ADR-0007)." >&2
		echo "Entries only in $proj (<) vs only on disk (>):" >&2
		diff "$tmp_proj" "$tmp_disk" | grep -E '^[<>]' >&2
		echo "Fix: add/remove the matching <ClCompile>/<ClInclude> entries in $proj (and its .filters)." >&2
		status=1
		rm -f "$tmp_disk" "$tmp_proj"
		return
	fi

	echo "OK: $proj matches $dir/*.cpp on disk ($(wc -l < "$tmp_disk" | tr -d ' ') files)."
	rm -f "$tmp_disk" "$tmp_proj"
}

check_dir Core Core/Core.vcxproj
check_dir Utilities Utilities/Utilities.vcxproj

exit $status
