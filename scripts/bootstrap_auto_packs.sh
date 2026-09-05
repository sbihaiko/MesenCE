#!/usr/bin/env bash
# Batch-regenerate the sibling auto/textures packs (ADR-0049/0147) of a ROM
# library, including the artist-legible sheets of ADR-0153 (Phase 9).
#
# Each ROM is staged into its own scratch folder and run through the *production*
# bootstrap (scripts/headless_record ... bootstrap): static tile export, then
# recording with screen capture, xBRZ 4x, into <stage>/<Game>/auto/textures.
# Staging matters for two reasons: the bootstrap only fires when nothing already
# dresses the ROM, and a game with a hand-made mep/ pack next to it would never
# bootstrap in place. Only auto/textures is installed back - auto/audio and any
# mep/ pack in the library are left untouched.
#
# Usage: scripts/bootstrap_auto_packs.sh <roms-dir> [seconds] [jobs] [stage-dir]
#
# Input: <lib>/<Game>/<Game>.play.txt wins when present (hand-tuned play for the
# golden games); otherwise the generic script below, which mashes Start/A for the
# first ~25 s to get through title and menu screens and then only moves, so it
# does not pause the game it just started. It reaches gameplay on many NES
# titles and on some it does not - scripts/sheet_report.py is how you tell which.
set -euo pipefail
cd "$(dirname "$0")/.."

LIB=${1:?usage: bootstrap_auto_packs.sh <roms-dir> [seconds] [jobs] [stage-dir]}
SECONDS_PER_ROM=${2:-300}
JOBS=${3:-4}
STAGE=${4:-$(mktemp -d)}
RECORDER=scripts/headless_record

[ -x "$RECORDER" ] || { echo "missing $RECORDER - run 'make capture-tool'" >&2; exit 1; }
mkdir -p "$STAGE"

GENERIC="$STAGE/generic.play.txt"
{
	# intro phase: work through title screens, file select and option menus
	for _ in $(seq 1 12); do
		echo "0.9 -"; echo "0.2 T"; echo "0.5 -"; echo "0.2 A"; echo "0.3 D"
	done
	# play phase: movement and actions, with a lone Start every ~12 s - enough to
	# leave a pause/inventory subscreen the intro phase may have opened, rare
	# enough not to keep pausing a game that is actually running
	for _ in $(seq 1 80); do
		echo "2 R"; echo "0.6 A"; echo "1.5 R"; echo "0.6 B"; echo "1.5 U"
		echo "0.6 A"; echo "1.5 L"; echo "0.6 B"; echo "1.5 D"; echo "0.6 A"
		echo "0.2 T"; echo "1 -"
	done
} > "$GENERIC"

record_one() {
	local rom="$1" stage="$2" secs="$3" generic="$4"
	local base name folder work script out
	base=$(basename "$rom")
	name=${base%.*}
	folder=$(dirname "$rom")/$name
	work="$stage/$name"
	script="$generic"
	[ -f "$folder/$name.play.txt" ] && script="$folder/$name.play.txt"

	rm -rf "$work"
	mkdir -p "$work"
	cp "$rom" "$work/"

	if ! "$RECORDER" "$work/$base" "$secs" "$work/out" bootstrap log "input=$script" > "$stage/$name.log" 2>&1; then
		echo "FAIL   $name (see $stage/$name.log)"
		return 0
	fi

	out="$work/$name/auto/textures"
	if [ ! -f "$out/hires.txt" ]; then
		echo "EMPTY  $name (bootstrap wrote no hires.txt)"
		return 0
	fi

	rm -rf "$folder/auto/textures"
	mkdir -p "$folder/auto"
	cp -R "$out" "$folder/auto/textures"

	local sheets=0 screens=0
	[ -d "$out/sheets" ] && sheets=$(/usr/bin/find "$out/sheets" -name '*.png' | grep -cv '\.orig\.png$' || true)
	[ -d "$out/backgrounds" ] && screens=$(/usr/bin/find "$out/backgrounds" -name 'screen*.png' | grep -cv '\.orig\.png$' || true)
	echo "OK     $name (sheets $sheets, screens $screens)"
}
export -f record_one
export RECORDER

echo "library : $LIB"
echo "staging : $STAGE"
echo "seconds : $SECONDS_PER_ROM   jobs: $JOBS"

/usr/bin/find "$LIB" -maxdepth 1 -name '*.nes' -print0 \
	| xargs -0 -P "$JOBS" -I{} bash -c 'record_one "$@"' _ {} "$STAGE" "$SECONDS_PER_ROM" "$GENERIC"

echo "done. staging kept at $STAGE"
