#!/usr/bin/env bash
# Build the native core and publish the macOS Mesen.app bundle (BundleApp),
# then optionally refresh the copy on the Desktop with a timestamped backup.
#
# This mirrors what the CI does (`.github/workflows/build.yml`) with the
# release flags, and adds two steps the CI does not need but a local
# Desktop refresh does:
#   1. inject the freshly built MesenCore.dylib into the published .app —
#      `dotnet publish -t:BundleApp` does NOT pick up a newly rebuilt
#      MesenCore.dylib when the C# build is up to date, so the .app would
#      otherwise ship the previous dylib.
#   2. ad-hoc codesign the bundle — macOS requires a valid (even adhoc)
#      signature on the app shell; a dylib overwrite can invalidate it.
#
# Usage:
#   scripts/build_app_macos.sh                # build + publish, keep the .app in bin/
#   scripts/build_app_macos.sh --desktop      # also refresh ~/Desktop/mesen/Mesen.app (backup first)
#   scripts/build_app_macos.sh --skip-tests   # skip the core-unit-tests gate
#
# en-US comments per the project convention (CLAUDE.md); the build itself
# delegates to the existing make targets.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

UPDATE_DESKTOP=0
RUN_TESTS=1
DESKTOP_DIR="$HOME/Desktop/mesen"

while [[ $# -gt 0 ]]; do
	case "$1" in
		--desktop) UPDATE_DESKTOP=1 ;;
		--skip-tests) RUN_TESTS=0 ;;
		--help|-h)
			cat <<-'EOF'
				Usage: scripts/build_app_macos.sh [--desktop] [--skip-tests]
				  --desktop      also refresh ~/Desktop/mesen/Mesen.app (timestamped backup)
				  --skip-tests   skip the core-unit-tests gate
			EOF
			exit 0
			;;
		*) echo "error: unknown option: $1" >&2; exit 1 ;;
	esac
	shift
done

# Detect the host architecture, mirroring the Makefile's MESENPLATFORM logic.
case "$(uname -m)" in
	x86_64)  MESENPLATFORM="osx-x64" ;;
	arm64|aarch64) MESENPLATFORM="osx-arm64" ;;
	*) echo "error: unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

# The published .app (BundleApp) lands here, matching the CI path.
PUBLISH_APP="$ROOT/bin/$MESENPLATFORM/Release/$MESENPLATFORM/publish/Mesen.app"
SHAREDLIB="MesenCore.dylib"
# The freshly built dylib from the core build.
CORE_DYLIB="$ROOT/InteropDLL/obj.$MESENPLATFORM/$SHAREDLIB"

echo "==> platform: $MESENPLATFORM"

echo "==> building native core (make core)"
make core

if [[ "$RUN_TESTS" == "1" ]]; then
	echo "==> running core unit tests (make core-unit-tests)"
	make core-unit-tests
fi

echo "==> publishing release .app (make ui DEBUG=0)"
make ui DEBUG=0

if [[ ! -d "$PUBLISH_APP" ]]; then
	echo "error: published app not found at $PUBLISH_APP" >&2
	exit 1
fi
if [[ ! -f "$CORE_DYLIB" ]]; then
	echo "error: freshly built dylib not found at $CORE_DYLIB" >&2
	echo "       (run 'make core' first if this is the first build)" >&2
	exit 1
fi

# `dotnet publish -t:BundleApp` caches the dylib copy; force the freshly
# built one into the bundle so the app actually carries the new core.
echo "==> injecting freshly built $SHAREDLIB into the .app"
cp -f "$CORE_DYLIB" "$PUBLISH_APP/Contents/MacOS/$SHAREDLIB"

# adhoc codesign so macOS accepts the (re-written) bundle.
echo "==> ad-hoc codesigning the .app"
codesign --force --deep --sign - "$PUBLISH_APP"

echo "==> done: $PUBLISH_APP"
stat -f '%Sm  %z  %N' -t '%Y-%m-%d %H:%M' "$PUBLISH_APP/Contents/MacOS/Mesen.dll" \
	"$PUBLISH_APP/Contents/MacOS/$SHAREDLIB"

if [[ "$UPDATE_DESKTOP" == "1" ]]; then
	DST="$DESKTOP_DIR/Mesen.app"
	if [[ ! -d "$DST" ]]; then
		echo "error: Desktop app not found at $DST; skipping refresh" >&2
		exit 1
	fi
	STAMP="$(date +%Y%m%d-%H%M%S)"
	echo "==> backing up current Desktop app to Mesen.app.bak-$STAMP"
	mv "$DST" "$DESKTOP_DIR/Mesen.app.bak-$STAMP"
	echo "==> copying published .app to Desktop"
	ditto "$PUBLISH_APP" "$DST"
	# ditto preserves resource forks/xattrs, which upsets loose codesign
	# verification; strip them and re-sign so the bundle is clean.
	find "$DST" -type f -exec xattr -c {} \; 2>/dev/null || true
	codesign --force --deep --sign - "$DST" 2>/dev/null || true
	echo "==> Desktop refreshed; backup kept at $DESKTOP_DIR/Mesen.app.bak-$STAMP"
	echo "    verify by checking the bundle ids/mtimes:"
	stat -f '      %Sm  %z  %N' -t '%Y-%m-%d %H:%M' \
		"$DST/Contents/MacOS/Mesen.dll" "$DST/Contents/MacOS/$SHAREDLIB"
fi
