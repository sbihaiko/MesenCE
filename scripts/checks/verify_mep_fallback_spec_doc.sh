#!/usr/bin/env bash
# Verifica docs/specs/MEP-v1.md (AC-9): a §2.1 documenta o fallback de
# subpasta como a regra de última prioridade da cadeia de convenções, e o
# texto nomeia a assimetria motor-vs-validadores (casamento por nome no
# motor C++ vs casamento estrutural em MepZipValidator.cs/mep_lint.py).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOC="$REPO_ROOT/docs/specs/MEP-v1.md"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$DOC" ] || fail "arquivo não encontrado: $DOC"

# Isola o texto da seção 2.1 (entre o heading "### 2.1" e o próximo "## 3").
SECTION_2_1="$(awk '/^### 2\.1 /{flag=1} /^## 3\. /{flag=0} flag' "$DOC")"
[ -n "$SECTION_2_1" ] || fail "não encontrei a seção ### 2.1 em $DOC"

echo "$SECTION_2_1" | grep -qi 'fallback' \
  || fail "§2.1 não menciona 'fallback' (regra de subpasta ausente)"

echo "$SECTION_2_1" | grep -qi 'menor prioridade\|última prioridade\|last-priority\|last priority' \
  || fail "§2.1 não afirma explicitamente que o fallback é a regra de menor/última prioridade"

# A regra de fallback deve vir depois da regra 7 (cadeia de precedência
# pasta irmã / HD Pack legado / contêineres centrais), não antes.
PRECEDENCE_LINE="$(grep -n 'Precedência entre origens' "$DOC" | head -1 | cut -d: -f1)"
FALLBACK_LINE="$(grep -ni 'fallback' "$DOC" | head -1 | cut -d: -f1)"
[ -n "$PRECEDENCE_LINE" ] || fail "não encontrei a regra 7 (cadeia de precedência) em $DOC"
[ -n "$FALLBACK_LINE" ] || fail "não encontrei a linha do fallback em $DOC"
if [ "$FALLBACK_LINE" -le "$PRECEDENCE_LINE" ]; then
  fail "o fallback (linha $FALLBACK_LINE) precisa vir DEPOIS da cadeia de precedência (linha $PRECEDENCE_LINE), não antes"
fi

# Nomeia a asimetria motor (nome) vs validadores (estrutural).
echo "$SECTION_2_1" | grep -qi 'assimetria' \
  || fail "§2.1 não usa o termo 'assimetria' para a divergência motor-vs-validadores"

echo "$SECTION_2_1" | grep -q 'PrepareZip' \
  || fail "§2.1 não referencia PrepareZip (o motor C++) na explicação da assimetria"

echo "$SECTION_2_1" | grep -q 'MepZipValidator.cs' \
  || fail "§2.1 não referencia MepZipValidator.cs (validador C#) na explicação da assimetria"

echo "$SECTION_2_1" | grep -q 'mep_lint.py' \
  || fail "§2.1 não referencia mep_lint.py (validador Python) na explicação da assimetria"

echo "$SECTION_2_1" | grep -qi 'casamento.*nome\|name.*match\|por nome' \
  || fail "§2.1 não descreve o critério do motor (casamento por nome)"

echo "$SECTION_2_1" | grep -qi 'estrutural\|structural' \
  || fail "§2.1 não descreve o critério dos validadores (casamento estrutural)"

echo "$SECTION_2_1" | grep -q 'ADR-0120' \
  || fail "§2.1 não referencia a ADR-0120 que documenta a decisão completa"

echo "PASS: docs/specs/MEP-v1.md §2.1 documenta o fallback como regra de última prioridade e nomeia a assimetria motor-vs-validadores (name vs structural)"
