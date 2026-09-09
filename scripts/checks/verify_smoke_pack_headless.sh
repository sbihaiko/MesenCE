#!/usr/bin/env bash
# F6.6 CI verifier: boots the real C++ core (scripts/headless_record, no GUI)
# against every F6.4c fixture recipe applied to a synthetic copyright-free
# NROM (scripts/gen_synthetic_nrom.py), asserting each installed pack loads
# with no missing <img>/<tile>/<background>/<bgm>/<sfx> target in the loader
# log. The missing-dep case is the "user-supplied audio not supplied" path
# and must report it as SKIPPED, not fail.
#
# Requires scripts/headless_record (built by `make capture-tool`). When it is
# missing - or older than a source it links against - the verifier builds it
# incrementally: under CI a build failure (or a missing toolchain) FAILs so the
# F6.6 gate can never silently no-op; locally it keeps verify_synthetic_nrom.sh's
# SKIP fallback so a docs-only edit does not demand a full core build.
#
# The staleness check is not a nicety: `make` does not build capture-tool (it is
# a separate target), so a change to the shared wire format
# (Utilities/LiveRecordFormat.h) leaves a harness linked against the previous
# signature, and it aborts at dyld time with `Symbol not found` - which this
# gate would otherwise report as a mysterious exit 134 on every fixture.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SMOKE="$REPO_ROOT/scripts/smoke_pack_headless.sh"
HARNESS="$REPO_ROOT/scripts/headless_record"
GEN_ROM="$REPO_ROOT/scripts/gen_synthetic_nrom.py"
RECIPE="$REPO_ROOT/scripts/mep_recipe.py"
FIXTURE="$REPO_ROOT/docs/specs/golden/mep-recipe/fixture"
PY="${PYTHON:-python3}"

[ -x "$SMOKE" ] || { echo "FAIL: $SMOKE not executable" >&2; exit 1; }
# Sources the harness links against: its own translation units plus the core
# library it resolves symbols from at load time.
HARNESS_DEPS=(
  "$REPO_ROOT/scripts/headless_record.cpp"
  "$REPO_ROOT/Core/Shared/Video/FrameCapture.cpp"
  "$REPO_ROOT/Utilities/LiveRecordFormat.h"
  "$REPO_ROOT/Utilities/LiveRecordFormat.cpp"
)
for dylib in "$REPO_ROOT"/InteropDLL/obj.*/MesenCore.*; do
  [ -f "$dylib" ] && HARNESS_DEPS+=("$dylib")
done

harness_is_stale() {
  [ ! -x "$HARNESS" ] && return 0
  local dep
  for dep in "${HARNESS_DEPS[@]}"; do
    [ -e "$dep" ] && [ "$dep" -nt "$HARNESS" ] && return 0
  done
  return 1
}

if harness_is_stale; then
  echo "building $HARNESS (make capture-tool)..." >&2
  BUILD_LOG="$(mktemp)"
  if ! (cd "$REPO_ROOT" && make -s capture-tool >"$BUILD_LOG" 2>&1); then
    if [ "${CI:-}" = "true" ]; then
      echo "FAIL: could not build $HARNESS (required for the F6.6 smoke in CI); build output:" >&2
      tail -n 60 "$BUILD_LOG" >&2
      rm -f "$BUILD_LOG"
      exit 1
    fi
    echo "SKIP: $HARNESS not built and could not be built (run 'make capture-tool' first)" >&2
    rm -f "$BUILD_LOG"
    exit 0
  fi
  rm -f "$BUILD_LOG"
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

AUDIO="$FIXTURE/audio-dep.zip"
ROM="$WORK/rom.nes"
"$PY" "$GEN_ROM" "$ROM" >/dev/null

FAILED=0

# run_case <recipe-name> <primary-zip> <expect-skip-audio: 0|1>
run_case() {
  local recipe="$1" primary="$2" expect_skip="$3"
  local out="$WORK/$(basename "$recipe" .json)"
  local args=(--primary "$FIXTURE/$primary")
  if [ "$expect_skip" != "1" ]; then
    args+=(--dep "audio=$AUDIO")
  fi
  if ! "$PY" "$RECIPE" apply "$FIXTURE/$recipe" "${args[@]}" --out "$out" >/dev/null 2>&1; then
    echo "FAIL: mep_recipe.py apply $recipe" >&2
    FAILED=1
    return
  fi

  local smoke_args=()
  [ "$expect_skip" = "1" ] && smoke_args+=(--allow-missing-audio)
  local log="$WORK/$(basename "$recipe" .json)-smoke.txt"
  if ! "$SMOKE" "$out" "$ROM" --work "$WORK/$(basename "$recipe" .json)-work" ${smoke_args[@]+"${smoke_args[@]}"} > "$log" 2>&1; then
    echo "FAIL: smoke $recipe" >&2
    sed 's/^/  /' "$log" >&2
    FAILED=1
    return
  fi
  if [ "$expect_skip" = "1" ] && ! grep -q "SKIP:" "$log"; then
    echo "FAIL: smoke $recipe expected a SKIPPED-audio note but found none" >&2
    sed 's/^/  /' "$log" >&2
    FAILED=1
    return
  fi
  echo "PASS: $recipe$([ "$expect_skip" = "1" ] && echo " (audio skipped)")"
}

run_case recipe.json primary.zip 0
run_case recipe-wrapped-subfolder.json wrapped-subfolder.zip 0
run_case recipe-nested-zip.json nested-zip.zip 0
run_case recipe-bare-probe.json bare-probe.zip 0
run_case recipe-missing-dep.json primary.zip 1

if [ "$FAILED" -ne 0 ]; then
  echo "FAIL: one or more smoke cases failed" >&2
  exit 1
fi
echo "PASS: all F6.4c fixture packs boot cleanly under scripts/smoke_pack_headless.sh"
