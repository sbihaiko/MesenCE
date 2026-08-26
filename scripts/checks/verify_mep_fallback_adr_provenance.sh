#!/usr/bin/env bash
# AC-8: .dev-squad/adr/0120-*.md states the provenance of the
# TasticHacks/Contra80s zip-structure claim (citing issue #3 and/or the
# release source it was described from), explicitly distinguishes what was
# independently verified by reading the current source (PrepareZip /
# DetectConventionLayout require an exact root layout with no recursion)
# from what was not independently re-verified (the real published zip's
# byte-for-byte structure), and qualifies any "would not load today" claim
# by that coverage gap instead of presenting it as an exhaustively confirmed
# fact. No mocks: reads the real ADR file from disk.
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

require_i() {
  # require_i <description> <ERE pattern>  — case-insensitive extended regex
  local desc="$1" pattern="$2"
  grep -qiE "$pattern" "$ADR" || fail "$desc: padrão '$pattern' não encontrado em $ADR"
}

require_f() {
  # require_f <description> <fixed string>
  local desc="$1" pattern="$2"
  grep -qF "$pattern" "$ADR" || fail "$desc: string '$pattern' não encontrada em $ADR"
}

# --- Provenance of the motivating claim ------------------------------------
require_i "menciona TasticHacks" "TasticHacks"
require_i "menciona Contra80s" "Contra80s"
require_i "cita a issue #3 e/ou a fonte de release" "issue #?3|issues/3"
grep -qiE "github\\.com/TasticHacks/Contra80s|releases/download" "$ADR" \
  || fail "não cita a fonte de release do pack (URL do GitHub Releases)"

# --- Independently verified vs. not independently re-verified --------------
require_i "marca algo como independentemente verificado" \
  "independently verified"
require_i "marca algo como NÃO re-verificado" \
  "not.*(independently )?(re-)?verified|not.*independently.*re-inspected|was not independently"

# The specific fact that WAS verified: PrepareZip / DetectConventionLayout
# require an exact root layout with no recursion.
require_f "menciona PrepareZip" "PrepareZip"
require_f "menciona DetectConventionLayout" "DetectConventionLayout"
require_i "afirma 'no recursion' para o comportamento atual" "no recursion"
require_i "cita o arquivo MepPackManager.cpp como fonte" "MepPackManager\\.cpp"
require_i "cita o arquivo MepPack.cpp como fonte" "MepPack\\.cpp"

# The specific fact that was NOT independently re-verified: the real
# published zip's byte-for-byte structure.
grep -qiE "byte-for-byte|actual (internal )?structure|real.*zip.*structure" "$ADR" \
  || fail "não menciona a estrutura byte-a-byte do zip real como não re-verificada"

# --- The "would not load today" claim must be qualified, not asserted flat -
if grep -qiE "would not load (today|as-is)" "$ADR"; then
  grep -qiE "qualif|coverage gap|gap\\)|described.*not independently|not.*independently re-inspected" "$ADR" \
    || fail "a afirmação 'would not load today' aparece sem qualificação explícita pela lacuna de verificação"
fi

echo "PASS: $ADR cita a proveniência TasticHacks/Contra80s (issue #3 / release), distingue o que foi verificado diretamente no código atual (PrepareZip/DetectConventionLayout sem recursão) do que não foi re-verificado (estrutura byte-a-byte do zip real) e qualifica qualquer afirmação de que o pack 'não carregaria hoje' por essa lacuna"
