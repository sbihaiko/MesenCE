#!/usr/bin/env bash
# Regression check for scripts/gen_synthetic_nrom.py: the copyright-free
# NROM fixture used to drive the real C++ HdPackLoader/MepPackManager
# against a submitted pack's hires.txt in CI (no real ROM ever needed,
# since ProcessBackgroundTag/ProcessConditionTag never read PRG/CHR bytes).
# Requires scripts/headless_record already built (`make capture-tool`).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GEN="$REPO_ROOT/scripts/gen_synthetic_nrom.py"
HARNESS="$REPO_ROOT/scripts/headless_record"
PY="${PYTHON:-python3}"

if [ ! -x "$HARNESS" ]; then
  echo "SKIP: $HARNESS not built (run 'make capture-tool' first)" >&2
  exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

ROM="$WORK/synthetic-test.nes"
"$PY" "$GEN" "$ROM" >/dev/null

LOG="$WORK/log.txt"
"$HARNESS" "$ROM" 1 "$WORK/out" log > "$LOG" 2>&1

if ! grep -q "\[iNes\] Mapper: 0 Sub: 0" "$LOG"; then
  echo "FAIL: synthetic ROM did not report as mapper 0" >&2
  cat "$LOG" >&2
  exit 1
fi
if ! grep -q "\[iNes\] PRG ROM: 32 KB" "$LOG"; then
  echo "FAIL: synthetic ROM did not report 32KB PRG" >&2
  cat "$LOG" >&2
  exit 1
fi
if grep -qi "error\|crash\|exception" "$LOG"; then
  echo "FAIL: unexpected error/crash booting the synthetic ROM" >&2
  cat "$LOG" >&2
  exit 1
fi

echo "PASS: synthetic NROM fixture boots cleanly under scripts/headless_record (mapper 0, 32KB PRG, no errors)"
