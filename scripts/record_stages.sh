#!/usr/bin/env bash
# F9.22 - per-stage recording batch.
#
# The retained OAM stream is capped at 4096 frames (kMaxSheetFrames), and
# gameplay almost never repeats a frame, so one long run loses its tail: the
# 120 s Contra golden run kept 4151 of 7213 frames. The right shape is several
# short runs, one per save state, each into its own pack folder, judged as a
# union. This script is that batch.
#
# Usage:
#   scripts/record_stages.sh <rom> <stages-dir> <out-dir> [seconds=60] [extra headless_record flags...]
#
# <stages-dir> holds pairs <stage>.mss + <stage>.txt (a save state and the
# input script that plays from it). A <stage>.txt with no .mss starts from
# power-on (the entry script itself). Each stage runs
#   headless_record <out>/<stage>/<rom name> <seconds> <out>/<stage>/rec bootstrap hdpack-off state=<stage>.mss input=<stage>.txt
# so the bootstrap builder writes <out>/<stage>/<rom stem>/auto/ - one pack per
# stage, nothing merged. The ROM is hard-linked (or copied) into each stage
# folder because the builder writes beside the ROM.
#
# To mint a state:  headless_record <rom> <seconds> <prefix> input=<entry.txt> save-state=<stages-dir>/<stage>.mss
set -euo pipefail

if [ $# -lt 3 ]; then
  sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
fi

rom="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
stages="$(cd "$2" && pwd)"
mkdir -p "$3"; out="$(cd "$3" && pwd)"
seconds="${4:-60}"
shift 3; [ $# -gt 0 ] && shift
extra=("$@")

here="$(cd "$(dirname "$0")" && pwd)"
record="$here/headless_record"
[ -x "$record" ] || { echo "missing $record - run: make capture-tool" >&2; exit 1; }
[ -f "$rom" ] || { echo "ROM not found: $rom" >&2; exit 1; }

romName="$(basename "$rom")"
shopt -s nullglob
scripts=("$stages"/*.txt)
[ ${#scripts[@]} -gt 0 ] || { echo "no <stage>.txt in $stages" >&2; exit 1; }

status=0
for script in "${scripts[@]}"; do
  stage="$(basename "${script%.txt}")"
  state="$stages/$stage.mss"
  dir="$out/$stage"
  mkdir -p "$dir"
  ln -f "$rom" "$dir/$romName" 2>/dev/null || cp "$rom" "$dir/$romName"
  # A previous pack would make the bootstrap skip the build (the .bootstrap
  # marker says "already done"); a stage run is always a fresh pack.
  rm -rf "$dir/${romName%.*}" "$dir/.bootstrap"
  args=("$dir/$romName" "$seconds" "$dir/rec" bootstrap hdpack-off "input=$script")
  [ -f "$state" ] && args+=("state=$state")
  echo "== $stage: ${args[*]} ${extra[*]:-}"
  # headless_record puts its mesen-home beside the output prefix, so every
  # stage gets its own home and log.
  if "$record" "${args[@]}" ${extra[@]+"${extra[@]}"} > "$dir/rec_stdout.log" 2>&1; then
    grep -h 'poses:' "$dir"/mesen-home/mesen.log 2>/dev/null | tail -1 || true
  else
    echo "   FAILED - see $dir/rec_stdout.log" >&2
    status=1
  fi
done
exit $status
