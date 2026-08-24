#!/usr/bin/env bash
# check-file-loc.sh <file> <max-lines>
#
# Machine-verifiable gate for the project's per-file line-count guardrails
# (e.g. the 200-line cap on Core/Shared/Audio/MidiExporter.cpp). Exits 0 if
# <file>'s line count is at or under <max-lines>, exits 1 if it's over, and
# exits 2 on a usage/IO error (missing args, file not found) so callers can
# tell "guardrail violated" apart from "couldn't even run the check".
set -euo pipefail

if [[ $# -ne 2 ]]; then
	echo "Usage: $0 <file> <max-lines>" >&2
	exit 2
fi

file="$1"
maxLines="$2"

if [[ ! -f "$file" ]]; then
	echo "error: file not found: $file" >&2
	exit 2
fi

if ! [[ "$maxLines" =~ ^[0-9]+$ ]]; then
	echo "error: <max-lines> must be a non-negative integer, got '$maxLines'" >&2
	exit 2
fi

lines=$(wc -l < "$file" | tr -d '[:space:]')

if (( lines > maxLines )); then
	echo "FAIL: $file has $lines lines (max $maxLines)" >&2
	exit 1
fi

echo "OK: $file has $lines lines (max $maxLines)"
exit 0
