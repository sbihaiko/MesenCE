#!/usr/bin/env bash
# build_app_macos.sh - local macOS Mesen.app build (core + BundleApp publish),
# with an optional refresh of the copy under ~/Desktop/mesen (timestamped
# backup first).
#
# Purpose: produce a runnable Release .app on a developer Mac that actually
# carries the MesenCore.dylib just compiled from the working tree, so a core
# change can be tried in the real GUI without waiting for CI. The build itself
# delegates to the existing make targets (`make core`, `make core-unit-tests`,
# `make ui DEBUG=0`), so the .app lands at the same path CI uses:
# bin/<osx-arm64|osx-x64>/Release/<rid>/publish/Mesen.app.
#
# What CI (.github/workflows/build.yml, macOS job) does NOT do and this
# script adds:
#   1. dylib injection - `dotnet publish -t:BundleApp` does not pick up a
#      newly rebuilt MesenCore.dylib when the C# build is already up to date,
#      so the freshly built InteropDLL/obj.<rid>/MesenCore.dylib is copied
#      over the one inside the bundle. CI always builds from a clean tree, so
#      it never hits this staleness.
#   2. ad-hoc codesign (`codesign --force --deep --sign -`) - macOS requires a
#      valid signature on the app shell and overwriting the dylib invalidates
#      the one the publish step produced. CI instead signs with the real
#      "Mesen" Developer ID certificate from repository secrets (hardened
#      runtime + entitlements) and only on non-PR builds; that identity is not
#      available locally, hence ad-hoc.
#   3. the Desktop refresh (--desktop): moves the current Desktop app to
#      Mesen.app.bak-<stamp>, copies the new bundle with `ditto`, strips
#      xattrs and re-signs ad-hoc. Purely a local convenience.
#
# Prerequisites: macOS with the Xcode Command Line Tools (clang, make,
# codesign, ditto, xattr) and a .NET SDK on PATH that matches the version
# pinned by UI/UI.csproj (`dotnet`); `make core-unit-tests` must pass unless
# --skip-tests is given. Nothing here is required by CI or by any other
# script; it is a developer convenience only.
#
# Usage:
#   scripts/build_app_macos.sh                # build + publish, keep the .app in bin/
#   scripts/build_app_macos.sh --desktop      # also refresh ~/Desktop/mesen/Mesen.app (backup first)
#   scripts/build_app_macos.sh --skip-tests   # skip the core-unit-tests gate
#
# Comments are en-US per the project convention (CLAUDE.md).

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
