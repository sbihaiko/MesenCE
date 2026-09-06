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
# Input scripts are counted in emulated frames (ADR-0157, F9.14): a "<n>f" step
# covers exactly n frames of the emulated console on any host load. The run also
# stops on a frame count, so [seconds] below sets a number of frames and the
# wall-clock time a batch takes is unrelated to it (the frame limiter is off).
#
# Input: <lib>/<Game>/<Game>.play.txt wins when present (hand-tuned play for the
# golden games); otherwise the generic script below, which mashes Start/A for the
# first ~25 s to get through title and menu screens and then only moves, so it
# does not pause the game it just started. It reaches gameplay on many NES
# titles and on some it does not, so each finished pack is run through the
# Verdicts: OK, OK* (a pack was written and the recorder still exited non-zero:
# the recording was cut short, so the pack is real but thinner than it should be
# -- see issue #165 for how that used to happen for no reason at all),
# MENU (the pack is real but the run never left the menus), EMPTY (no hires.txt)
# and FAIL (no hires.txt and a non-zero exit).
#
# F9.13 criterion (scripts/gameplay_probe.py): a recording that never got past
# the menus is reported as MENU with the reason, never as OK. The criterion has
# a declared blind spot - see that script's docstring - so MENU is trustworthy
# and OK is "nothing caught it", not a guarantee.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

LIB=${1:?usage: bootstrap_auto_packs.sh <roms-dir> [seconds] [jobs] [stage-dir]}
SECONDS_PER_ROM=${2:-300}
JOBS=${3:-4}
STAGE=${4:-$(mktemp -d)}
RECORDER=scripts/headless_record

[ -x "$RECORDER" ] || { echo "missing $RECORDER - run 'make capture-tool'" >&2; exit 1; }
mkdir -p "$STAGE"

GENERIC="$STAGE/generic.play.txt"
{
	# Steps are in emulated frames (ADR-0157): a step is a position in a menu
	# sequence, and counting it in host seconds made it land on a different
	# frame on a loaded machine. The counts below are the pre-F9.14 seconds at
	# the NTSC rate (0.2 s = 12f, 0.9 s = 54f, ...).
	# intro phase: work through title screens, file select and option menus
	for _ in $(seq 1 12); do
		echo "54f -"; echo "12f T"; echo "30f -"; echo "12f A"; echo "18f D"
	done
	# play phase: movement and actions, with a lone Start every ~12 s - enough to
	# leave a pause/inventory subscreen the intro phase may have opened, rare
	# enough not to keep pausing a game that is actually running
	for _ in $(seq 1 80); do
		echo "120f R"; echo "36f A"; echo "90f R"; echo "36f B"; echo "90f U"
		echo "36f A"; echo "90f L"; echo "36f B"; echo "90f D"; echo "36f A"
		echo "12f T"; echo "60f -"
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

	local rc=0
	"$RECORDER" "$work/$base" "$secs" "$work/out" bootstrap log "input=$script" > "$stage/$name.log" 2>&1 || rc=$?

	out="$work/$name/auto/textures"
	if [ ! -f "$out/hires.txt" ]; then
		# No pack: the exit code is the only thing to report, and it matters.
		if [ "$rc" -ne 0 ]; then
			echo "FAIL   $name (exit $rc, see $stage/$name.log)"
		else
			echo "EMPTY  $name (bootstrap wrote no hires.txt)"
		fi
		return 0
	fi
	# A pack is on disk. A non-zero exit after that is a real signal and is kept
	# visible, but it is not a reason to throw away the recording: the pack is
	# built from whatever frames the run did cover, so it is thinner, not wrong.
	# On 2026-09-05 eight of thirty runs exited non-zero this way; the cause was
	# a watchdog that budgeted wall clock from the recording's *emulated*
	# seconds, which stopped meaning anything once the frame limiter came off
	# (#165). Judge the artefact, report the code.

	rm -rf "$folder/auto/textures"
	mkdir -p "$folder/auto"
	cp -R "$out" "$folder/auto/textures"

	local sheets=0 screens=0 probe verdict
	[ -d "$out/sheets" ] && sheets=$(/usr/bin/find "$out/sheets" -name '*.png' | grep -cv '\.orig\.png$' || true)
	[ -d "$out/backgrounds" ] && screens=$(/usr/bin/find "$out/backgrounds" -name 'screen*.png' | grep -cv '\.orig\.png$' || true)

	# F9.13: "sheets N, screens N" says nothing about whether the run got past
	# the menus, so ask the criterion and print its reason when it says no.
	probe=$(python3 "$ROOT/scripts/gameplay_probe.py" "$out" 2>/dev/null | head -1 || true)
	verdict=$(printf '%s' "$probe" | cut -f1)
	local exited=""
	[ "$rc" -ne 0 ] && exited=" [truncated run, recorder exited $rc -- see $stage/$name.log]"
	if [ "$verdict" = "menu-only" ]; then
		echo "MENU   $name (sheets $sheets, screens $screens) - $(printf '%s' "$probe" | cut -f3)$exited"
	elif [ -n "$exited" ]; then
		echo "OK*    $name (sheets $sheets, screens $screens)$exited"
	else
		echo "OK     $name (sheets $sheets, screens $screens)"
	fi
}
export -f record_one
export RECORDER ROOT

echo "library : $LIB"
echo "staging : $STAGE"
echo "seconds : $SECONDS_PER_ROM   jobs: $JOBS"

/usr/bin/find "$LIB" -maxdepth 1 -name '*.nes' -print0 \
	| xargs -0 -P "$JOBS" -I{} bash -c 'record_one "$@"' _ {} "$STAGE" "$SECONDS_PER_ROM" "$GENERIC"

echo "done. staging kept at $STAGE"
