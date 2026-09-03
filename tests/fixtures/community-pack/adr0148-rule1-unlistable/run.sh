#!/usr/bin/env bash
# ADR-0148 rule 1 — local refusal check (on-demand, calls a model; not CI-blocking).
#
# Builds the fixture zip from ./pack and drives it through the real local
# harness (scripts/validate_pack_local.sh) with the real
# .github/ai/validate-classify.md prompt, offline: no GitHub issue, no
# network fetch, no writes.
#
# Usage: tests/fixtures/community-pack/adr0148-rule1-unlistable/run.sh [--injection] [--model <model>]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# --injection: same unlistable pack, but the pack file names, the bundled
# README and the issue text all try to instruct the classifier to accept it.
# Proves the prompt treats them as DATA, never as instruction.
PACK_DIR="pack"; BODY="issue_body.md"; NAME="adr0148-rule1"
case "${1:-}" in
  --injection)
    PACK_DIR="pack-injection"; BODY="issue_body_injection.md"; NAME="adr0148-rule1-injection"
    shift
    ;;
  # --ext-injection: the clean unlistable pack, but the issue's "External
  # assets" field (the {{EXTERNAL_ASSETS_SUFFIX}} slot, issue #152) carries
  # only injection prose - no dependency URL - plus a forged
  # EXTERNAL-ASSETS-DATA-END sentinel. That slot used to be wrapped by the
  # renderer in imperative text; it is now fenced as data, so the exception
  # must NOT fire (nothing is declared) and the verdict must stay invalid.
  --ext-injection)
    PACK_DIR="pack"; BODY="issue_body_ext_injection.md"; NAME="adr0148-rule1-ext-injection"
    shift
    ;;
esac
ROOT="$(cd "$HERE/../../../.." && pwd)"
WORK="${WORK:-$ROOT/.cache/validate-local/$NAME}"
ZIP="$WORK/unlistable-audio-pack.zip"
mkdir -p "$WORK"
rm -f "$ZIP"
( cd "$HERE/$PACK_DIR" && zip -q -X -r "$ZIP" . )
cd "$ROOT"
exec bash scripts/validate_pack_local.sh 9999 \
  --pack-file "$ZIP" \
  --issue-body "$HERE/$BODY" \
  --work "$WORK" "$@"
