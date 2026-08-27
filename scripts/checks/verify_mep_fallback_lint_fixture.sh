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
grep -q "structural fallback (ADR-0120)" <<<"$RUN_OUT" \
  || fail "mep_lint.py aceitou o pack Contra80s-shaped mas não emitiu a linha info do fallback:
$RUN_OUT"
grep -qF "pack root discovered at 'Contra80s-v1.1/Contra (U) [!]' (depth 4)" <<<"$RUN_OUT" \
  || fail "a linha info do fallback não nomeia o path/depth descobertos como esperado:
$RUN_OUT"
grep -q "0 error(s)" <<<"$RUN_OUT" || fail "pack Contra80s-shaped aceito mas o resumo não reporta 0 erro(s):
$RUN_OUT"

run_lint "$REJECT_ZIP"
[ "$RUN_RC" -ne 0 ] || fail "mep_lint.py aceitou o pack ambíguo de dois subdiretórios (esperava exit != 0):
$RUN_OUT"
grep -q "no section found" <<<"$RUN_OUT" \
  || fail "pack ambíguo não foi rejeitado com 'nenhuma seção encontrada':
$RUN_OUT"
grep -q "structural fallback (ADR-0120)" <<<"$RUN_OUT" \
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
grep -q "structural fallback (ADR-0120)" <<<"$RUN_OUT" \
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
grep -q "invalid JSON" <<<"$RUN_OUT" \
  || fail "pack.json malformado sob o prefixo do fallback não foi reportado como JSON inválido:
$RUN_OUT"
grep -qF "$ACCEPT_WRAPPER_PACK_JSON" <<<"$RUN_OUT" \
  || fail "o erro de JSON inválido não referencia o pack.json dentro do prefixo descoberto (deveria, não o da raiz do container):
$RUN_OUT"

# --- fixture 5: sections.textures.path == "" under a fallback prefix -------
"$PY" "$GEN_FALLBACK" "$WORK/fallback" empty-path >/dev/null \
  || fail "gen_mep_fallback_test_pack.py falhou ao gerar 'empty-path'"
EMPTY_PATH_ZIP="$WORK/fallback/mep-fallback-empty-section-path.zip"
[ -f "$EMPTY_PATH_ZIP" ] || fail "fixture 'empty-path' não foi gerada: $EMPTY_PATH_ZIP"

run_lint "$EMPTY_PATH_ZIP"
[ "$RUN_RC" -ne 0 ] || fail "mep_lint.py aceitou um pack com sections.textures.path==\"\" e hires.txt quebrado sob o prefixo do fallback (esperava exit != 0 — a barra dupla root_prefix+path vazio não pode silenciar a camada textures):
$RUN_OUT"
grep -q "does not exist: missing.png" <<<"$RUN_OUT" \
  || fail "o hires.txt quebrado (path==\"\") sob o prefixo do fallback não foi lintado (nenhum erro <img> reportado):
$RUN_OUT"

# --- fixture 6: loose root hires.txt under a fallback prefix, no pack.json -
"$PY" "$GEN_FALLBACK" "$WORK/fallback" root-hires >/dev/null \
  || fail "gen_mep_fallback_test_pack.py falhou ao gerar 'root-hires'"
ROOT_HIRES_ZIP="$WORK/fallback/mep-fallback-root-hires.zip"
[ -f "$ROOT_HIRES_ZIP" ] || fail "fixture 'root-hires' não foi gerada: $ROOT_HIRES_ZIP"

run_lint "$ROOT_HIRES_ZIP"
[ "$RUN_RC" -ne 0 ] || fail "mep_lint.py aceitou um hires.txt quebrado solto na raiz do subdiretório descoberto (sem pack.json, esperava exit != 0 — o branch de hires.txt-na-raiz precisa ser espelhado sob o prefixo do fallback):
$RUN_OUT"
grep -q "does not exist: missing.png" <<<"$RUN_OUT" \
  || fail "o hires.txt legado (raiz do fallback) não foi lintado (nenhum erro <img> reportado):
$RUN_OUT"

# --- fixture 7: zip-slip-shaped candidate ('..' segment) -------------------
"$PY" "$GEN_FALLBACK" "$WORK/fallback" traversal >/dev/null \
  || fail "gen_mep_fallback_test_pack.py falhou ao gerar 'traversal'"
TRAVERSAL_ZIP="$WORK/fallback/mep-fallback-traversal.zip"
[ -f "$TRAVERSAL_ZIP" ] || fail "fixture 'traversal' não foi gerada: $TRAVERSAL_ZIP"

run_lint "$TRAVERSAL_ZIP"
[ "$RUN_RC" -ne 0 ] || fail "SEGURANÇA: mep_lint.py aceitou um candidato zip-slip-shaped ('../evil/...') via fallback estrutural (esperava exit != 0 — find_fallback_subfolder deve recusar via safe_rel):
$RUN_OUT"
grep -q "no section found" <<<"$RUN_OUT" \
  || fail "candidato zip-slip-shaped não foi rejeitado com 'nenhuma seção encontrada':
$RUN_OUT"
grep -q "structural fallback (ADR-0120)" <<<"$RUN_OUT" \
  && fail "SEGURANÇA: candidato zip-slip-shaped não deveria emitir a linha info do fallback (deveria ser recusado antes disso):
$RUN_OUT"

echo "PASS: mep_lint.py aceita o pack Contra80s-shaped via fallback estrutural (com info de path/depth), rejeita o pack ambíguo de dois subdiretórios, rejeita um pack.json malformado descoberto via fallback, rejeita sections.textures.path==\"\" com hires.txt quebrado sob o fallback, rejeita um hires.txt legado quebrado solto na raiz do fallback, rejeita um candidato zip-slip-shaped ('..'), e não muda a classificação de um pack.json-root pack existente"
