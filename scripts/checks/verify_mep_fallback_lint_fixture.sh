#!/usr/bin/env bash
# AC-5: scripts/mep_lint.py's structural fallback discovery (ADR-0120),
# driven by the new scripts/gen_mep_fallback_test_pack.py fixtures:
#   - accepts the Contra80s-shaped wrapper-folder zip (no root pack.json,
#     zip name != ROM name — the existing conventions already fail by
#     construction) and emits an info line naming the discovered path and
#     depth;
#   - rejects the ambiguous two-subfolder zip (two structurally valid,
#     distinct candidate roots) with the pre-existing "nenhuma seção
#     encontrada" error, same as before this ADR;
#   - leaves an existing-convention fixture's classification unchanged: a
#     root-pack.json zip from the pre-existing scripts/gen_mep_test_pack.py
#     must still pass, with NO fallback info line at all (the fallback must
#     never even run when the existing conventions already matched);
#   - rejects a fallback-discovered subfolder whose pack.json is malformed:
#     pack.json is one of the FALLBACK_SUFFIXES accept markers, so this
#     proves the discovered manifest is fully linted (not just used as an
#     unchecked structural signal) once the fallback resolves a prefix.
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

[ -f "$LINT" ] || fail "não encontrado: $LINT"
[ -f "$GEN_FALLBACK" ] || fail "não encontrado: $GEN_FALLBACK"
[ -f "$GEN_EXISTING" ] || fail "não encontrado: $GEN_EXISTING"

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
  || fail "gen_mep_fallback_test_pack.py falhou"

ACCEPT_ZIP="$WORK/fallback/mep-fallback-accept.zip"
REJECT_ZIP="$WORK/fallback/mep-fallback-reject.zip"
[ -f "$ACCEPT_ZIP" ] || fail "fixture 'accept' não foi gerada: $ACCEPT_ZIP"
[ -f "$REJECT_ZIP" ] || fail "fixture 'reject' não foi gerada: $REJECT_ZIP"

run_lint "$ACCEPT_ZIP"
[ "$RUN_RC" -eq 0 ] || fail "mep_lint.py rejeitou o pack Contra80s-shaped (esperava exit 0, achou $RUN_RC):
$RUN_OUT"
grep -q "fallback estrutural (ADR-0120)" <<<"$RUN_OUT" \
  || fail "mep_lint.py aceitou o pack Contra80s-shaped mas não emitiu a linha info do fallback:
$RUN_OUT"
grep -qF "raiz do pack descoberta em 'Contra80s-v1.1/Contra (U) [!]' (depth 4)" <<<"$RUN_OUT" \
  || fail "a linha info do fallback não nomeia o path/depth descobertos como esperado:
$RUN_OUT"
grep -q "0 erro(s)" <<<"$RUN_OUT" || fail "pack Contra80s-shaped aceito mas o resumo não reporta 0 erro(s):
$RUN_OUT"

run_lint "$REJECT_ZIP"
[ "$RUN_RC" -ne 0 ] || fail "mep_lint.py aceitou o pack ambíguo de dois subdiretórios (esperava exit != 0):
$RUN_OUT"
grep -q "nenhuma seção encontrada" <<<"$RUN_OUT" \
  || fail "pack ambíguo não foi rejeitado com 'nenhuma seção encontrada':
$RUN_OUT"
grep -q "fallback estrutural (ADR-0120)" <<<"$RUN_OUT" \
  && fail "pack ambíguo não deveria emitir a linha info do fallback (candidato deveria ser recusado por ambiguidade):
$RUN_OUT"

# --- fixture 3: regression via the pre-existing gen_mep_test_pack.py -------
# A synthetic ROM: no-intro sha1 only needs bytes to hash, not a real game.
DUMMY_ROM="$WORK/dummy.nes"
printf 'NES\x1a\x02\x01\x00\x00%080d' 0 > "$DUMMY_ROM"

"$PY" "$GEN_EXISTING" "$DUMMY_ROM" "$WORK/existing" zip >/dev/null \
  || fail "gen_mep_test_pack.py falhou"
EXISTING_ZIP="$WORK/existing/mep-test-zip.zip"
[ -f "$EXISTING_ZIP" ] || fail "fixture de regressão não foi gerada: $EXISTING_ZIP"

run_lint "$EXISTING_ZIP"
[ "$RUN_RC" -eq 0 ] || fail "regressão: pack com pack.json na raiz deixou de ser aceito (exit $RUN_RC):
$RUN_OUT"
grep -q "fallback estrutural (ADR-0120)" <<<"$RUN_OUT" \
  && fail "regressão: um pack.json-root pack não deveria nunca acionar o fallback estrutural:
$RUN_OUT"

# --- fixture 4: malformed manifest under a fallback-discovered prefix ------
"$PY" "$GEN_FALLBACK" "$WORK/fallback" malformed >/dev/null \
  || fail "gen_mep_fallback_test_pack.py falhou ao gerar 'malformed'"
MALFORMED_ZIP="$WORK/fallback/mep-fallback-malformed-manifest.zip"
[ -f "$MALFORMED_ZIP" ] || fail "fixture 'malformed' não foi gerada: $MALFORMED_ZIP"

run_lint "$MALFORMED_ZIP"
[ "$RUN_RC" -ne 0 ] || fail "mep_lint.py aceitou um pack.json malformado descoberto via fallback (esperava exit != 0 — o manifest descoberto precisa ser lintado, não só usado como marcador de aceite):
$RUN_OUT"
grep -q "JSON inválido" <<<"$RUN_OUT" \
  || fail "pack.json malformado sob o prefixo do fallback não foi reportado como JSON inválido:
$RUN_OUT"
grep -qF "$ACCEPT_WRAPPER_PACK_JSON" <<<"$RUN_OUT" \
  || fail "o erro de JSON inválido não referencia o pack.json dentro do prefixo descoberto (deveria, não o da raiz do container):
$RUN_OUT"

echo "PASS: mep_lint.py aceita o pack Contra80s-shaped via fallback estrutural (com info de path/depth), rejeita o pack ambíguo de dois subdiretórios, rejeita um pack.json malformado descoberto via fallback, e não muda a classificação de um pack.json-root pack existente"
