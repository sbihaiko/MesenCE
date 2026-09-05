#!/usr/bin/env bash
# F6.6 — headless load smoke for an installed community pack.
#
# Boots the real C++ core (scripts/headless_record, no GUI) against a ROM
# with the pack installed beside it (bootstrap convention, ADR-0044/0049:
# the pack folder is a sibling of the ROM), then asserts the loader log
# carries no missing-target warnings for any <img>/<tile>/<background>/<bgm>/
# <sfx> target the pack's hires.txt references. Texture packs must tick
# frames (the emulation must run the requested seconds without dying); audio
# packs must register every declared track (an <bgm>/<sfx> whose OGG is
# missing logs "OGG file not found" and fails the smoke).
#
# Missing-target gate signatures (all in the loader log, matching the
# HdPackLoader logError macro and its siblings):
#   "[HDPack - Line N] ... could not be read"              -> missing <img> PNG
#   "[HDPack - Line N] Error while loading background: X"  -> missing <background> PNG
#   "[HDPack - Line N] Invalid bitmap index: N"            -> <tile> referencing a
#                                                             bitmap that never loaded
#   "[HDPack - Line N] OGG file not found: X"              -> missing <bgm>/<sfx> OGG
#   "[HDPack] PNG file X is invalid."                      -> present-but-corrupt PNG
#                                                             (no "- Line N" prefix)
#   "[MEP] ... section has no loadable hires.txt"          -> a declared section never
#                                                             loaded (nothing validated)
# A positive load signal ("[MEP] textures: loaded NES HD pack from" /
# "[MEP] audio: ... BGM / ... SFX tracks") must also appear for a declared
# section, so a pack that is detected but whose textures never load FAILs
# instead of passing vacuously.
#
# The <patch> tag / patches[] entry is NOT in the smoke's gate scope — the
# F6.6 acceptance checks img/tile/background/bgm/sfx targets only. A "patch
# skipped" / "Patch file not found" line is reported as info: a synthetic
# ROM never matches the pack's target sha1, and the pack.json patches[] flow
# already gates patches at the MEP layer (ADR-0138 §6).
#
# User-supplied external audio (e.g. the LiQuiDz OGGs, distributed outside
# the pack zip) is smoked only when the audio is supplied locally; pass
# --allow-missing-audio to report the missing OGGs as SKIPPED instead of
# failing — the rest of the pack is still validated.
#
# The ROM is a user-supplied No-Intro image (never redistributed) or a
# homebrew test ROM such as scripts/gen_synthetic_nrom.py's output for CI.
#
# Usage:
#   scripts/smoke_pack_headless.sh <installed-pack-dir> <rom> [--seconds N]
#       [--work DIR] [--allow-missing-audio] [--errata FILE]
#
#   <installed-pack-dir>   the pack folder as installed (post-recipe: has
#                          hires.txt — at the root or at the textures section
#                          path — plus the textures/audio the manifest names)
#   <rom>                  ROM to boot (copied into a scratch sibling layout)
#   --seconds N            boot seconds (default 2)
#   --work DIR             scratch dir (default .cache/smoke-pack-headless/<rom>)
#   --allow-missing-audio  report missing <bgm>/<sfx> OGGs as SKIPPED, not FAIL
#   --errata FILE          ADR-0152 known-missing declarations; the named
#                          <img>/<background> targets report as DECLARED
#                          instead of FAIL. Auto-resolved from the installed
#                          .mep-install.json's SourceSha256 when not given.
#                          Read through scripts/mep_errata.py — the same parser
#                          mep_lint.py uses, so the two gates cannot drift
#                          (which is what bug #155 was).
#
# Exit: 0 = PASS (or PASS with SKIPPED audio), 1 = FAIL.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HARNESS="$REPO_ROOT/scripts/headless_record"
PY="${PYTHON:-python3}"

SECONDS_BOOT=2
ALLOW_MISSING_AUDIO=0
WORK=""
ERRATA=""

#The header block above is the usage text; USAGE_END tracks its last line
#so adding an option never silently truncates --help.
USAGE_END=62
usage() {
	sed -n "2,${USAGE_END}p" "${BASH_SOURCE[0]}" | sed -E 's/^# ?//'
	exit 2
}

# --- arg parsing ---
POSITIONAL=()
while [[ $# -gt 0 ]]; do
	case "$1" in
		--seconds) [[ $# -ge 2 ]] || usage; SECONDS_BOOT="$2"; shift 2 ;;
		--work) [[ $# -ge 2 ]] || usage; WORK="$2"; shift 2 ;;
		--allow-missing-audio) ALLOW_MISSING_AUDIO=1; shift ;;
		--errata) [[ $# -ge 2 ]] || usage; ERRATA="$2"; shift 2 ;;
		--help|-h) usage ;;
		-*) echo "error: unknown option $1" >&2; usage ;;
		*) POSITIONAL+=("$1"); shift ;;
	esac
done
[[ ${#POSITIONAL[@]} -eq 2 ]] || usage
[[ "$SECONDS_BOOT" =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "error: --seconds must be a number" >&2; usage; }
PACK_DIR="${POSITIONAL[0]}"
ROM="${POSITIONAL[1]}"

# --- pre-flight ---
[[ -x "$HARNESS" ]] || { echo "FAIL: $HARNESS not built (run 'make capture-tool' first)" >&2; exit 1; }
[[ -f "$ROM" ]] || { echo "FAIL: ROM not found: $ROM" >&2; exit 1; }
[[ -d "$PACK_DIR" ]] || { echo "FAIL: installed pack dir not found: $PACK_DIR" >&2; exit 1; }

# The manifest is the pack's hires.txt — at the root, or under the textures
# section path when pack.json says so (MEP-v1 §3.2 allows a non-root
# "sections.textures.path"). Resolve it so a textures/-laid-out pack is not
# refused; the loader-log gates below still do the real assertion.
resolve_manifest() {
	if [[ -f "$PACK_DIR/pack.json" ]]; then
		"$PY" -c "
import json, sys
p = json.load(open(sys.argv[1]))
s = (p.get('sections') or {}).get('textures') or {}
path = (s.get('path') or '').strip('/')
print((sys.argv[2] + '/' + path + '/hires.txt') if path else (sys.argv[2] + '/hires.txt'))
" "$PACK_DIR/pack.json" "$PACK_DIR"
	else
		echo "$PACK_DIR/hires.txt"
	fi
}
MANIFEST="$(resolve_manifest)"

# ADR-0152: resolve the known-missing errata for this pack. Explicit --errata
# wins; otherwise the installed .mep-install.json names the artifact it came
# from (SourceSha256), which is the errata's file name. A pack installed by
# hand has no stamp and simply gets no errata.
if [[ -z "$ERRATA" && -f "$PACK_DIR/.mep-install.json" ]]; then
	SRC_SHA="$("$PY" -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print(''); raise SystemExit
# The install stamp writes source.sha256 (43); the install registry outside
# mep/ writes SourceSha256. Accept both so either shape resolves an errata.
src = d.get('source') or {}
print(str(src.get('sha256') or d.get('SourceSha256') or '').strip())
" "$PACK_DIR/.mep-install.json")"
	if [[ -n "$SRC_SHA" ]]; then
		ERRATA="$("$PY" "$REPO_ROOT/scripts/mep_errata.py" resolve "$REPO_ROOT/docs/community-packs/errata" "$SRC_SHA" || true)"
	fi
fi
if [[ -n "$ERRATA" ]]; then
	[[ -f "$ERRATA" ]] || { echo "FAIL: errata file not found: $ERRATA" >&2; exit 1; }
	"$PY" "$REPO_ROOT/scripts/mep_errata.py" validate "$ERRATA" >/dev/null || {
		echo "FAIL: errata file is invalid: $ERRATA" >&2; exit 1; }
fi

# Is this missing target declared known-missing? Delegates to the same parser
# mep_lint.py imports, so a target the lint pardons and this gate fails (or the
# reverse) is not expressible - that divergence was bug #155.
declared() {
	[[ -n "$ERRATA" ]] || return 1
	"$PY" "$REPO_ROOT/scripts/mep_errata.py" covers "$ERRATA" "$MANIFEST" "$1" "$2"
}
[[ -f "$MANIFEST" ]] || { echo "FAIL: no hires.txt manifest (looked at $MANIFEST)" >&2; exit 1; }

ROM_BASE="$(basename "$ROM")"
ROM_EXT="${ROM_BASE##*.}"
ROM_NAME="${ROM_BASE%.*}"

if [[ -z "$WORK" ]]; then
	WORK="$REPO_ROOT/.cache/smoke-pack-headless/$ROM_NAME"
fi
mkdir -p "$WORK/roms" "$WORK/out"
rm -rf "$WORK/roms/$ROM_NAME"
cp "$ROM" "$WORK/roms/$ROM_BASE"
cp -R "$PACK_DIR" "$WORK/roms/$ROM_NAME"

# --- boot the core with the pack as the ROM's sibling ---
LOG="$WORK/log.txt"
# The harness copies MesenNesDB.txt from the repo-root cwd, so run from there.
# The exit code is NOT discarded: a hard crash (SIGSEGV/SIGABRT) kills the
# harness before any "emulation stopped" line, and must fail the smoke.
set +e
(cd "$REPO_ROOT" && ./scripts/headless_record "$WORK/roms/$ROM_BASE" "$SECONDS_BOOT" "$WORK/out/x" log) > "$LOG" 2>&1
HARNESS_EXIT=$?
set -e

# The harness dumps MessageManager's in-memory log, a ring capped at 1000
# entries (Core/Shared/MessageManager.cpp). A pack that logs more than that
# while loading pushes its own earliest lines -- including the "[MEP] pack ...
# matches ROM sha1" detection line, which is the very first message of the run
# -- out of the dump before it is printed, so asserting against it reported a
# working pack as undetected (#160: issue-148 Metroid HD, 8234 loader
# messages). MessageManager also writes an uncapped <home>/mesen.log; when it
# is there, assert against that instead, keeping the harness's own boot lines
# (they are not core-log messages and appear only on stdout).
ASSERT_LOG="$WORK/assert-log.txt"
CORE_LOG="$WORK/out/mesen-home/mesen.log"
if [[ -s "$CORE_LOG" ]]; then
	sed -n '1,/^--- core log ---$/p' "$LOG" > "$ASSERT_LOG"
	# mesen.log timestamps each line ("HH:MM:SS.mmm "); the dump does not, and
	# every matcher below keys on the "[HDPack...]" prefix, so strip them.
	sed -E 's/^[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3} //' "$CORE_LOG" >> "$ASSERT_LOG"
else
	cp "$LOG" "$ASSERT_LOG"
fi

# --- assert against the loader log ---
fail_lines=()
skipped_lines=()
declared_lines=()

if [[ "$HARNESS_EXIT" -ne 0 ]]; then
	fail_lines+=("boot: headless_record exited $HARNESS_EXIT (hard crash / load failure?)")
fi
if ! grep -q "ROM loaded" "$ASSERT_LOG"; then
	fail_lines+=("boot: ROM did not load (no 'ROM loaded' line)")
fi
if grep -q "emulation stopped unexpectedly\|failed to load ROM" "$ASSERT_LOG"; then
	fail_lines+=("boot: emulation died during the run")
fi

# The MEP sibling scan must have detected the pack; without this line the
# smoke validated nothing (the pack was silently not loaded).
if ! grep -q "\[MEP\] pack .* matches ROM sha1" "$ASSERT_LOG"; then
	# Fail closed, but never blame the pack for a capture we could not read:
	# without mesen.log the dump may simply have been truncated (#160), and an
	# absent line then proves nothing either way.
	if [[ -s "$CORE_LOG" ]]; then
		fail_lines+=("pack: no '[MEP] pack ... matches ROM sha1' line — the sibling pack was not detected")
	else
		fail_lines+=("pack: INCONCLUSIVE — no detection line, and no uncapped $CORE_LOG to rule out a truncated capture")
	fi
fi
if grep -q "\[MEP\] rejected sibling folder\|has no textures/, audio/ or synth/ layer" "$ASSERT_LOG"; then
	fail_lines+=("pack: rejected or ignored by the MEP loader")
fi

# A declared section that never loads must fail, not pass vacuously.
if grep -q "section has no loadable hires.txt" "$ASSERT_LOG"; then
	fail_lines+=("missing target: a declared section never loaded (see diagnostics)")
fi

# Missing-target scan. Every logError line carries "[HDPack - Line N] ";
# the corrupt-PNG message "[HDPack] PNG file X is invalid." does not, so it
# is matched on its own line. Anything else under those prefixes is a
# non-gate loader diagnostic (e.g. the <patch> tag), surfaced as info.
while IFS= read -r line; do
	msg="${line##*] }"
	if [[ "$line" == *"Error while loading background"* ]]; then
		target="${msg##*: }"
		if declared background "$target"; then
			declared_lines+=("<background> $target")
		else
			fail_lines+=("missing target: $msg")
		fi
	elif [[ "$line" == *"could not be read"* ]]; then
		# "Error loading HDPack: PNG file <src> could not be read."
		target="${msg#*PNG file }"; target="${target% could not be read.}"
		if declared img "$target"; then
			declared_lines+=("<img> $target")
		else
			fail_lines+=("missing target: $msg")
		fi
	elif [[ "$line" == *"Invalid bitmap index"* || "$line" == *"PNG file"*"is invalid"* ]]; then
		# Not a missing target: the file is present and wrong. An errata says
		# "we checked, it is absent", which would be a false statement here, so
		# these are never declarable (mep_errata.KNOWN_TAGS).
		fail_lines+=("missing target: $msg")
	elif [[ "$line" == *"OGG file not found"* ]]; then
		if [[ "$ALLOW_MISSING_AUDIO" == "1" ]]; then
			skipped_lines+=("$msg")
		else
			fail_lines+=("missing target: $msg")
		fi
	fi
done < <(grep -E "\[HDPack - Line [0-9]+\]|\[HDPack\] PNG file" "$ASSERT_LOG" || true)

# --- report ---
echo "--- loader diagnostics ($(basename "$PACK_DIR")) ---"
# Collapsed: a large pack can log thousands of identical lines (8222
# "Condition not found" for issue-148), which would bury the report.
grep -E "\[HDPack|\[MEP\]" "$ASSERT_LOG" \
	| sed -E 's/ - Line [0-9]+\]/]/' \
	| sort | uniq -c | sort -rn \
	| sed -E 's/^ *1 (.*)$/  \1/; s/^ *([0-9]+) (.*)$/  \2  [x\1]/' || true
echo "--- result ---"
for l in ${fail_lines[@]+"${fail_lines[@]}"}; do
	echo "  FAIL: $l"
done
for l in ${skipped_lines[@]+"${skipped_lines[@]}"}; do
	echo "  SKIP: $l"
done
for l in ${declared_lines[@]+"${declared_lines[@]}"}; do
	echo "  DECLARED: $l — known-missing per $(basename "$ERRATA") (ADR-0152)"
done

if [[ ${#fail_lines[@]} -eq 0 ]]; then
	suffix=""
	if [[ ${#declared_lines[@]} -gt 0 ]]; then
		suffix=", ${#declared_lines[@]} known-missing target(s) declared by errata"
	fi
	if [[ ${#skipped_lines[@]} -gt 0 ]]; then
		echo "PASS (${#skipped_lines[@]} user-supplied OGG(s) skipped — not supplied locally$suffix)"
	else
		echo "PASS: boots with no missing img/tile/background/bgm/sfx targets$suffix"
	fi
	exit 0
fi
echo "FAIL: $(basename "$PACK_DIR") has missing targets or failed to load"
exit 1
