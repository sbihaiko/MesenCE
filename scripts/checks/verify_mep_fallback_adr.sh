#!/usr/bin/env bash
# AC-7: .dev-squad/adr/0120-*.md documents the zip subfolder fallback as:
#   (a) an additive, lowest-priority extension of ADR-0040/ADR-0049's
#       discovery precedence (not a reordering of it);
#   (b) a pure, I/O-free function that PrepareZip consults, with
#       PrepareZip's outFolder contract held fixed (no signature change);
#   (c) the C++ (name match) vs C#/Python (structural match) asymmetry,
#       together with its named follow-up (an optional ROM-name parameter);
#   (d) the standalone C++ E2E zip-pipeline test harness explicitly
#       deferred as a separate, not-this-task follow-up.
# No mocks: reads the real ADR file from disk.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADR_GLOB=("$REPO_ROOT"/.dev-squad/adr/0120-*.md)

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -e "${ADR_GLOB[0]}" ] || fail "nenhum arquivo .dev-squad/adr/0120-*.md encontrado"
[ "${#ADR_GLOB[@]}" -eq 1 ] || fail "esperava exatamente 1 arquivo 0120-*.md, achou ${#ADR_GLOB[@]}: ${ADR_GLOB[*]}"

ADR="${ADR_GLOB[0]}"

MIN_LINES=40
LINE_COUNT="$(wc -l < "$ADR" | tr -d ' ')"
[ "$LINE_COUNT" -ge "$MIN_LINES" ] || fail "$ADR tem só $LINE_COUNT linhas (esperado >= $MIN_LINES; parece trivial)"

# Flattened (newlines -> spaces) copy for multi-word phrase checks that may
# legitimately wrap across source lines in the prose.
FLAT="$(tr '\n' ' ' < "$ADR")"

require() {
  # require <description> <pattern...>  — every pattern must be found
  # (fixed-string, case-sensitive) somewhere in the ADR.
  local desc="$1"; shift
  local pattern
  for pattern in "$@"; do
    grep -qF "$pattern" "$ADR" || fail "$desc: não encontrou '$pattern' em $ADR"
  done
}

# (a) additive, lowest-priority extension of ADR-0040/ADR-0049 precedence
require "referencia ADR-0040" "ADR-0040"
require "referencia ADR-0049" "ADR-0049"
grep -qiE "additive|adiciona|last-priority|lowest-priority|fourth" "$ADR" \
  || fail "não descreve a regra como adição de última prioridade (additive/last-priority)"
grep -qiE "precedence" "$ADR" || fail "não menciona a cadeia de precedência"
echo "$FLAT" | grep -qiE "without reordering|never reorder|não reordena|not reordered|unchanged.*precedence|precedence.*unchanged" \
  || fail "não afirma explicitamente que a precedência existente NÃO é reordenada"

# (b) pure, I/O-free function; PrepareZip's outFolder contract held fixed
require "menciona PrepareZip" "PrepareZip"
grep -qiE "pure|I/O-free|no I/O|I\\O-free|sem I/O" "$ADR" \
  || fail "não descreve a função como pura/I/O-free"
grep -qF "outFolder" "$ADR" || fail "não menciona outFolder"
grep -qiE "contract.*(fixed|unchanged)|signature.*(fixed|unchanged|stays exactly)|held fixed" "$ADR" \
  || fail "não afirma que o contrato/assinatura de PrepareZip fica inalterado"

# (c) C++ (name) vs C#/Python (structural) asymmetry + named follow-up
grep -qiE "asymmetry|assimetria" "$ADR" || fail "não nomeia a assimetria C++ vs C#/Python"
require "menciona MepZipValidator" "MepZipValidator"
require "menciona mep_lint.py" "mep_lint.py"
grep -qiE "name match|by name|name-based" "$ADR" || fail "não descreve o lado C++ como match por nome"
grep -qiE "structural|structure match" "$ADR" || fail "não descreve o lado C#/Python como match estrutural"
grep -qiE "ROM-name parameter|ROM name parameter|optional.*ROM.*name" "$ADR" \
  || fail "não nomeia o follow-up de parâmetro opcional de nome de ROM"
grep -qiE "follow-up|follow up" "$ADR" || fail "não marca o item como follow-up nomeado"

# (d) standalone C++ E2E zip-pipeline harness deferred as separate follow-up
grep -qiE "E2E|end-to-end" "$ADR" || fail "não menciona o harness E2E"
grep -qiE "deferred|separate.*follow-up|not-this-task" "$ADR" \
  || fail "não marca o harness E2E como deferido/fora deste task"
grep -qiE "ZipReader" "$ADR" || fail "não conecta o harness deferido ao link de ZipReader/miniz"

echo "PASS: $ADR documenta (a) extensão aditiva de última prioridade sobre ADR-0040/ADR-0049, (b) função pura sem I/O com o contrato outFolder de PrepareZip fixo, (c) a assimetria C++ (nome) vs C#/Python (estrutura) com seu follow-up nomeado, e (d) o harness E2E C++ deferido"
