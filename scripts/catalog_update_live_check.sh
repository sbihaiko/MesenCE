#!/usr/bin/env bash
# P.6 — on-demand live check of the F6.4b catalog-update coordinator path.
#
# Boots the real client against a ROM that a LIVE catalog row matches, lets
# CommunityPackCatalogFetcher + CommunityPackInstallCoordinator run for real
# (real HTTP to raw.githubusercontent.com for docs/community-packs.json, real
# HTTP to the row's artifact host), and asserts the coordinator's verdict line
# is in the emulator log:
#
#   [CommunityPackInstall] update verdict=<NotInstalled|UpToDate|Updated|WrapperOnly|NoDowngrade|RemovedFromCatalog> …
#
# That line is emitted by UI/Services/CommunityPackInstallCoordinator.cs
# (EvaluateGates), i.e. it is the observable proof that the P.6 update
# decision (UI/Logic/CommunityCatalogUpdateDecision.cs, 15 unit tests) ran
# against a real catalog entry rather than a fixture.
#
# ---------------------------------------------------------------------------
# WHY THIS IS NOT WIRED INTO CI OR ANY BUILD-BLOCKING TEST
# ---------------------------------------------------------------------------
#   * External hosts. It fetches the catalog from raw.githubusercontent.com
#     and the pack artifact from GitHub releases / Google Drive / MediaFire.
#     None of those is under this project's control.
#   * Rate limits. Unauthenticated raw.githubusercontent.com and, far more
#     aggressively, Google Drive throttle repeated automated downloads (Drive
#     answers a quota interstitial instead of the file); artifacts run to
#     hundreds of MB.
#   * Outages / mutation. A branch archive (…/archive/refs/heads/<b>.zip) is
#     re-generated on every push, so its bytes — and the pass/fail of the
#     hash check — change without any commit here (ADR-0146/ADR-0148).
#   * It needs a real display and a real ROM. The client is the Avalonia GUI
#     app, and the ROM is a user-supplied No-Intro image that is never
#     redistributed with this repo.
# A non-deterministic, network- and display-dependent check has no business
# gating a build. Run it by hand when the P.6 path needs re-confirming.
# The deterministic half of P.6 is already covered by UI.Tests
# (CommunityCatalogUpdateDecision) and stays the CI gate.
#
# Usage:
#   scripts/catalog_update_live_check.sh <rom> [options]
#
#   <rom>                  ROM to boot; must be matched by a live catalog row
#                          (No-Intro PRG+CHR sha1 vs the row's rom.sha1/sha1s)
#   --app <Mesen.app>      app bundle (default: the Release publish output)
#   --home <dir>           Mesen home folder holding mesen.log (default:
#                          ~/Library/Application Support/MesenCE)
#   --seconds N            how long to leave the client running (default 40)
#   --expect <verdict>     fail unless the observed verdict equals this
#   --no-launch            catalog phase only: resolve the live row for the
#                          ROM and stop, without starting the GUI. Useful to
#                          confirm the network half on a headless machine.
#   --keep-log <file>      copy the captured log here
#
# Exit: 0 = a verdict line was observed (and matched --expect, if given),
#       1 = it was not, 2 = usage/prerequisite error.
#
# Related on-demand scripts (same "not in CI" shape):
#   scripts/validate_pack_local.sh    — local run of the CI classify pipeline
#   scripts/smoke_pack_headless.sh    — F6.6 load smoke of an installed pack
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"

# The exact URL CommunityPackCatalogFetcher.CatalogUrl uses - keep in sync.
CATALOG_URL="https://raw.githubusercontent.com/sbihaiko/MesenCE/main/docs/community-packs.json"

APP="$REPO_ROOT/bin/osx-arm64/Release/osx-arm64/publish/Mesen.app"
HOME_FOLDER="$HOME/Library/Application Support/MesenCE"
RUN_SECONDS=40
EXPECT=""
NO_LAUNCH=0
KEEP_LOG=""

usage() {
	sed -n '2,60p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
	exit 2
}

POSITIONAL=()
while [[ $# -gt 0 ]]; do
	case "$1" in
		--app) [[ $# -ge 2 ]] || usage; APP="$2"; shift 2 ;;
		--home) [[ $# -ge 2 ]] || usage; HOME_FOLDER="$2"; shift 2 ;;
		--seconds) [[ $# -ge 2 ]] || usage; RUN_SECONDS="$2"; shift 2 ;;
		--expect) [[ $# -ge 2 ]] || usage; EXPECT="$2"; shift 2 ;;
		--keep-log) [[ $# -ge 2 ]] || usage; KEEP_LOG="$2"; shift 2 ;;
		--no-launch) NO_LAUNCH=1; shift ;;
		--help|-h) usage ;;
		-*) echo "error: unknown option $1" >&2; usage ;;
		*) POSITIONAL+=("$1"); shift ;;
	esac
done
[[ ${#POSITIONAL[@]} -eq 1 ]] || usage
ROM="${POSITIONAL[0]}"
[[ -f "$ROM" ]] || { echo "error: ROM not found: $ROM" >&2; exit 2; }
command -v curl >/dev/null || { echo "error: curl is required" >&2; exit 2; }
command -v "$PY" >/dev/null || { echo "error: python3 is required" >&2; exit 2; }

# --- phase 1: the live catalog, fetched the way the client fetches it -------
echo "--- live catalog ---"
CATALOG_JSON="$(mktemp -t mesence-catalog)"
trap 'rm -f "$CATALOG_JSON"' EXIT
HTTP_STATUS="$(curl -sS -o "$CATALOG_JSON" -w '%{http_code}' --max-time 30 "$CATALOG_URL" || echo 000)"
echo "  GET $CATALOG_URL -> HTTP $HTTP_STATUS ($(wc -c < "$CATALOG_JSON" | tr -d ' ') bytes)"
if [[ "$HTTP_STATUS" != "200" ]]; then
	echo "BLOCKED: the live catalog could not be fetched (HTTP $HTTP_STATUS) - external host or network" >&2
	exit 1
fi

# No-Intro sha1 = sha1 of PRG+CHR, i.e. the file minus its 16-byte iNES
# header (plus a 512-byte trainer when flags6 bit 2 is set) - the same rule
# MepPackManager::ComputeNoIntroSha1 applies, and the one the catalog's
# rom.sha1/rom.sha1s carry (ADR-0003/ADR-0039).
MATCH_JSON="$("$PY" - "$ROM" "$CATALOG_JSON" <<'PYEOF'
import hashlib, json, sys

rom_path, catalog_path = sys.argv[1], sys.argv[2]
data = open(rom_path, "rb").read()
offset = 0
if data[:4] == b"NES\x1a":
    offset = 16 + (512 if len(data) > 6 and (data[6] & 0x04) else 0)
no_intro = hashlib.sha1(data[offset:]).hexdigest().upper()
whole = hashlib.sha1(data).hexdigest().upper()

catalog = json.load(open(catalog_path))
hit = None
for pack in catalog.get("packs") or []:
    rom = pack.get("rom") or {}
    hashes = {h.upper() for h in ([rom.get("sha1")] + (rom.get("sha1s") or [])) if h}
    if hashes & {no_intro, whole}:
        hit = pack
        break
print(json.dumps({"no_intro": no_intro, "whole": whole, "entry": hit}))
PYEOF
)"

"$PY" - "$MATCH_JSON" <<'PYEOF'
import json, sys
info = json.loads(sys.argv[1])
print("  rom no-intro sha1: " + info["no_intro"])
print("  rom whole-file sha1: " + info["whole"])
entry = info["entry"]
if entry is None:
    print("  matching catalog row: NONE")
else:
    print("  matching catalog row: %s (issue %s)" % (entry.get("pack_id"), entry.get("issue")))
    print("    game=%s kind=%s" % (entry.get("game"), entry.get("kind")))
    print("    content_id=%s" % entry.get("content_id"))
    print("    sha256=%s" % entry.get("sha256"))
    print("    url=%s" % entry.get("url"))
PYEOF

if ! "$PY" -c "import json,sys; sys.exit(0 if json.loads(sys.argv[1])['entry'] else 1)" "$MATCH_JSON"; then
	# The client also has a game-name fallback (CommunityPackCatalogMatcher),
	# but a sha1 hit is what makes this check deterministic - say so plainly
	# instead of launching and reading an ambiguous log.
	echo "BLOCKED: no live catalog row matches this ROM by sha1; pick a ROM that one does" >&2
	exit 1
fi

if [[ "$NO_LAUNCH" == "1" ]]; then
	echo "--- result ---"
	echo "  SKIPPED (--no-launch): catalog phase only, the coordinator was not run"
	exit 0
fi

# --- phase 2: run the real client and read its log --------------------------
BIN="$APP/Contents/MacOS/Mesen"
[[ -x "$BIN" ]] || { echo "error: app binary not found: $BIN (build it with scripts/build_app_macos.sh)" >&2; exit 2; }
LOG="$HOME_FOLDER/mesen.log"
mkdir -p "$HOME_FOLDER"

echo "--- running the client ---"
echo "  $BIN \"$ROM\" (${RUN_SECONDS}s)"
LOG_MTIME_BEFORE=""
[[ -f "$LOG" ]] && LOG_MTIME_BEFORE="$(stat -f %m "$LOG" 2>/dev/null || stat -c %Y "$LOG")"
# MessageManager rotates <home>/mesen.log to mesen.log.1 on the first message
# of a session, so the file read afterwards belongs to this run alone.
"$BIN" "$ROM" >/dev/null 2>&1 &
APP_PID=$!
SLEPT=0
while [[ "$SLEPT" -lt "$RUN_SECONDS" ]]; do
	kill -0 "$APP_PID" 2>/dev/null || break
	sleep 1
	SLEPT=$((SLEPT + 1))
done
kill "$APP_PID" 2>/dev/null || true
wait "$APP_PID" 2>/dev/null || true

[[ -f "$LOG" ]] || { echo "error: no log at $LOG (wrong --home?)" >&2; exit 2; }
LOG_MTIME_AFTER="$(stat -f %m "$LOG" 2>/dev/null || stat -c %Y "$LOG")"
if [[ "$LOG_MTIME_AFTER" == "$LOG_MTIME_BEFORE" ]]; then
	# The client never logged anything, so the log below is a previous
	# session's. The usual cause is no interactive desktop session: the
	# Avalonia app needs a real GUI login (it will not start over ssh, from a
	# detached agent shell, or from a launchd context with no window server),
	# and this check has no headless mode - the coordinator only runs inside
	# the client.
	echo "BLOCKED: $LOG was not written during the run - the client did not start." >&2
	echo "         Run this from a terminal inside a logged-in desktop session." >&2
	exit 2
fi
[[ -n "$KEEP_LOG" ]] && cp "$LOG" "$KEEP_LOG"

echo "--- community-pack log lines ---"
grep -E "\[CommunityPack" "$LOG" | sed 's/^/  /' || true

VERDICT_LINE="$(grep -E "\[CommunityPackInstall\] update verdict=" "$LOG" | tail -1 || true)"
echo "--- result ---"
if [[ -z "$VERDICT_LINE" ]]; then
	echo "  FAIL: no '[CommunityPackInstall] update verdict=' line in $LOG"
	echo "        (the fetch or the download+verify aborted before the gate; see the lines above)"
	exit 1
fi
VERDICT="$(sed -E 's/.*update verdict=([A-Za-z]+).*/\1/' <<<"$VERDICT_LINE")"
echo "  observed: $VERDICT_LINE"
if [[ -n "$EXPECT" && "$VERDICT" != "$EXPECT" ]]; then
	echo "  FAIL: expected verdict=$EXPECT, got verdict=$VERDICT"
	exit 1
fi
echo "PASS: coordinator ran against the live catalog (verdict=$VERDICT)"
exit 0
