#!/usr/bin/env bash
# AC-5: scripts/mep_lint.py's structural fallback discovery (ADR-0120),
# driven by the new scripts/gen_mep_fallback_test_pack.py fixtures:
#   - accepts the Contra80s-shaped wrapper-folder zip (no root pack.json,
#     zip name != ROM name — the existing conventions already fail by
#     construction) and emits an info line naming the discovered path and
#     depth;
#   - rejects the ambiguous two-subfolder zip (two structurally valid,
#     distinct candidate roots) with the pre-existing "no section found"
#     error, same as before this ADR;
#   - leaves an existing-convention fixture's classification unchanged: a
#     root-pack.json zip from the pre-existing scripts/gen_mep_test_pack.py
#     must still pass, with NO fallback info line at all (the fallback must
#     never even run when the existing conventions already matched);
#   - rejects a fallback-discovered subfolder whose pack.json is malformed:
#     pack.json is one of the FALLBACK_SUFFIXES accept markers, so this
#     proves the discovered manifest is fully linted (not just used as an
#     unchecked structural signal) once the fallback resolves a prefix.
#   - rejects a fallback-discovered pack.json whose sections.textures.path
#     is "" (hires.txt at the discovered subfolder's own root, not under
#     "textures/"): regression for the root_prefix + empty-path double-slash
#     bug that silently dropped that layer's hires.txt from linting.
#   - rejects a fallback-discovered subfolder with a loose root hires.txt
#     (HD-pack-legado layout, no pack.json at all): regression for the
#     container-root-only "hires.txt na raiz" branch not being mirrored
#     under the discovered prefix, which left the textures layer mute.
#   - rejects a zip-slip-shaped candidate ("../evil/textures/hires.txt"):
#     security regression for find_fallback_subfolder discovering a '..'
#     segment as a pack root instead of refusing it via safe_rel (revision
#     cycle T3) — must fail closed exactly like the ambiguous-two-subfolder
#     fixture, not silently accept an out-of-container path.
# No mocks: runs the real mep_lint.py CLI against real generated zip files.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${PYTHON:-python3}"
LINT="$REPO_ROOT/scripts/mep_lint.py"
GEN_FALLBACK="$REPO_ROOT/scripts/gen_mep_fallback_test_pack.py"
GEN_EXISTING="$REPO_ROOT/scripts/gen_mep_test_pack.py"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$LINT" ] || fail "not found: $LINT"
[ -f "$GEN_FALLBACK" ] || fail "not found: $GEN_FALLBACK"
[ -f "$GEN_EXISTING" ] || fail "not found: $GEN_EXISTING"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Mirrors ACCEPT_WRAPPER in gen_mep_fallback_test_pack.py.
ACCEPT_WRAPPER_PACK_JSON="Contra80s-v1.1/Contra (U) [!]/pack.json"

run_lint() {
  # run_lint <zip> -> stdout on global RUN_OUT, exit code on global RUN_RC
  set +e
  RUN_OUT="$("$PY" "$LINT" "$1" 2>&1)"
  RUN_RC=$?
  set -e
}

# --- fixtures 1/2: the new ADR-0120 fallback generator ---------------------
"$PY" "$GEN_FALLBACK" "$WORK/fallback" accept reject >/dev/null \
  || fail "gen_mep_fallback_test_pack.py failed"

ACCEPT_ZIP="$WORK/fallback/mep-fallback-accept.zip"
REJECT_ZIP="$WORK/fallback/mep-fallback-reject.zip"
[ -f "$ACCEPT_ZIP" ] || fail "'accept' fixture was not generated: $ACCEPT_ZIP"
[ -f "$REJECT_ZIP" ] || fail "'reject' fixture was not generated: $REJECT_ZIP"

run_lint "$ACCEPT_ZIP"
[ "$RUN_RC" -eq 0 ] || fail "mep_lint.py rejected the Contra80s-shaped pack (expected exit 0, got $RUN_RC):
$RUN_OUT"
grep -q "structural fallback (ADR-0120)" <<<"$RUN_OUT" \
  || fail "mep_lint.py accepted the Contra80s-shaped pack but did not emit the fallback info line:
$RUN_OUT"
grep -qF "pack root discovered at 'Contra80s-v1.1/Contra (U) [!]' (depth 4)" <<<"$RUN_OUT" \
  || fail "the fallback info line does not name the discovered path/depth as expected:
$RUN_OUT"
grep -q "0 error(s)" <<<"$RUN_OUT" || fail "Contra80s-shaped pack accepted but the summary does not report 0 error(s):
$RUN_OUT"

run_lint "$REJECT_ZIP"
[ "$RUN_RC" -ne 0 ] || fail "mep_lint.py accepted the ambiguous two-subfolder pack (expected exit != 0):
$RUN_OUT"
grep -q "no section found" <<<"$RUN_OUT" \
  || fail "the ambiguous pack was not rejected with 'no section found':
$RUN_OUT"
grep -q "structural fallback (ADR-0120)" <<<"$RUN_OUT" \
  && fail "the ambiguous pack should not emit the fallback info line (the candidate should be refused for ambiguity):
$RUN_OUT"

# --- fixture 3: regression via the pre-existing gen_mep_test_pack.py -------
# A synthetic ROM: no-intro sha1 only needs bytes to hash, not a real game.
DUMMY_ROM="$WORK/dummy.nes"
printf 'NES\x1a\x02\x01\x00\x00%080d' 0 > "$DUMMY_ROM"

"$PY" "$GEN_EXISTING" "$DUMMY_ROM" "$WORK/existing" zip >/dev/null \
  || fail "gen_mep_test_pack.py failed"
EXISTING_ZIP="$WORK/existing/mep-test-zip.zip"
[ -f "$EXISTING_ZIP" ] || fail "regression fixture was not generated: $EXISTING_ZIP"

run_lint "$EXISTING_ZIP"
[ "$RUN_RC" -eq 0 ] || fail "regression: pack with pack.json at the root is no longer accepted (exit $RUN_RC):
$RUN_OUT"
grep -q "structural fallback (ADR-0120)" <<<"$RUN_OUT" \
  && fail "regression: a pack.json-root pack should never trigger the structural fallback:
$RUN_OUT"

# --- fixture 4: malformed manifest under a fallback-discovered prefix ------
"$PY" "$GEN_FALLBACK" "$WORK/fallback" malformed >/dev/null \
  || fail "gen_mep_fallback_test_pack.py failed generating 'malformed'"
MALFORMED_ZIP="$WORK/fallback/mep-fallback-malformed-manifest.zip"
[ -f "$MALFORMED_ZIP" ] || fail "'malformed' fixture was not generated: $MALFORMED_ZIP"

run_lint "$MALFORMED_ZIP"
[ "$RUN_RC" -ne 0 ] || fail "mep_lint.py accepted a malformed pack.json discovered via the fallback (expected exit != 0 — the discovered manifest must be linted, not just used as an accept marker):
$RUN_OUT"
grep -q "invalid JSON" <<<"$RUN_OUT" \
  || fail "the malformed pack.json under the fallback prefix was not reported as invalid JSON:
$RUN_OUT"
grep -qF "$ACCEPT_WRAPPER_PACK_JSON" <<<"$RUN_OUT" \
  || fail "the invalid-JSON error does not reference the pack.json inside the discovered prefix (it should, not the container root's):
$RUN_OUT"

# --- fixture 5: sections.textures.path == "" under a fallback prefix -------
"$PY" "$GEN_FALLBACK" "$WORK/fallback" empty-path >/dev/null \
  || fail "gen_mep_fallback_test_pack.py failed generating 'empty-path'"
EMPTY_PATH_ZIP="$WORK/fallback/mep-fallback-empty-section-path.zip"
[ -f "$EMPTY_PATH_ZIP" ] || fail "'empty-path' fixture was not generated: $EMPTY_PATH_ZIP"

run_lint "$EMPTY_PATH_ZIP"
[ "$RUN_RC" -ne 0 ] || fail "mep_lint.py accepted a pack with sections.textures.path==\"\" and a broken hires.txt under the fallback prefix (expected exit != 0 — the root_prefix + empty-path double slash must not silence the textures layer):
$RUN_OUT"
grep -q "does not exist: missing.png" <<<"$RUN_OUT" \
  || fail "the broken hires.txt (path==\"\") under the fallback prefix was not linted (no <img> error reported):
$RUN_OUT"

# --- fixture 6: loose root hires.txt under a fallback prefix, no pack.json -
"$PY" "$GEN_FALLBACK" "$WORK/fallback" root-hires >/dev/null \
  || fail "gen_mep_fallback_test_pack.py failed generating 'root-hires'"
ROOT_HIRES_ZIP="$WORK/fallback/mep-fallback-root-hires.zip"
[ -f "$ROOT_HIRES_ZIP" ] || fail "'root-hires' fixture was not generated: $ROOT_HIRES_ZIP"

run_lint "$ROOT_HIRES_ZIP"
[ "$RUN_RC" -ne 0 ] || fail "mep_lint.py accepted a broken hires.txt loose at the root of the discovered subfolder (no pack.json, expected exit != 0 — the root-hires.txt branch must be mirrored under the fallback prefix):
$RUN_OUT"
grep -q "does not exist: missing.png" <<<"$RUN_OUT" \
  || fail "the legacy hires.txt (fallback root) was not linted (no <img> error reported):
$RUN_OUT"

# --- fixture 7: zip-slip-shaped candidate ('..' segment) -------------------
"$PY" "$GEN_FALLBACK" "$WORK/fallback" traversal >/dev/null \
  || fail "gen_mep_fallback_test_pack.py failed generating 'traversal'"
TRAVERSAL_ZIP="$WORK/fallback/mep-fallback-traversal.zip"
[ -f "$TRAVERSAL_ZIP" ] || fail "'traversal' fixture was not generated: $TRAVERSAL_ZIP"

run_lint "$TRAVERSAL_ZIP"
[ "$RUN_RC" -ne 0 ] || fail "SECURITY: mep_lint.py accepted a zip-slip-shaped candidate ('../evil/...') via the structural fallback (expected exit != 0 — find_fallback_subfolder must refuse it via safe_rel):
$RUN_OUT"
grep -q "no section found" <<<"$RUN_OUT" \
  || fail "the zip-slip-shaped candidate was not rejected with 'no section found':
$RUN_OUT"
grep -q "structural fallback (ADR-0120)" <<<"$RUN_OUT" \
  && fail "SECURITY: the zip-slip-shaped candidate should not emit the fallback info line (it should be refused before that):
$RUN_OUT"

echo "PASS: mep_lint.py accepts the Contra80s-shaped pack via the structural fallback (with path/depth info), rejects the ambiguous two-subfolder pack, rejects a malformed pack.json discovered via the fallback, rejects sections.textures.path==\"\" with a broken hires.txt under the fallback, rejects a broken legacy hires.txt loose at the fallback root, rejects a zip-slip-shaped candidate ('..'), and does not change the classification of an existing pack.json-root pack"
