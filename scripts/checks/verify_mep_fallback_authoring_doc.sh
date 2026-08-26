#!/usr/bin/env bash
# Verifica docs/hd-pack-authoring.md (AC-10): documenta, para autores, o
# caminho de compatibilidade de última prioridade para zips de release que
# embrulham o pack numa subpasta/pasta de promoção (o fallback de MEP-v1.md
# §2.1 regra 9).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOC="$REPO_ROOT/docs/hd-pack-authoring.md"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$DOC" ] || fail "arquivo não encontrado: $DOC"

grep -qi 'wrapper\|promo' "$DOC" \
  || fail "$DOC não menciona pasta de wrapper/promoção em zips de release"

grep -qi 'subpasta' "$DOC" \
  || fail "$DOC não menciona a busca por subpasta (fallback)"

grep -q 'MEP-v1.md' "$DOC" \
  || fail "$DOC não referencia MEP-v1.md"

grep -q '§2.1' "$DOC" \
  || fail "$DOC não referencia a seção §2.1 de MEP-v1.md (onde o fallback é normativo)"

grep -qi 'última prioridade\|last.priority\|último recurso' "$DOC" \
  || fail "$DOC não deixa claro que o fallback é de última prioridade/último recurso"

grep -qi 'ambigu' "$DOC" \
  || fail "$DOC não menciona a rejeição por ambiguidade (mais de uma subpasta candidata)"

grep -qi 'mep_lint.py' "$DOC" \
  || fail "$DOC não menciona que a triagem automática (mep_lint.py) também aplica o fallback"

# A recomendação continua sendo evitar depender do fallback, preferindo as
# convenções de primeira classe (pack.json na raiz / zip nomeado como a ROM).
grep -qi 'pack.json na raiz' "$DOC" \
  || fail "$DOC não recomenda pack.json na raiz como alternativa preferida ao fallback"

echo "PASS: docs/hd-pack-authoring.md documenta o caminho de compatibilidade de wrapper/promoção apontando para MEP-v1.md §2.1"
