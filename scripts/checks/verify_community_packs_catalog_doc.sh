#!/usr/bin/env bash
# AC-8: docs/community-packs.md existe, com o header de tabela esperado
# (link/jogo/console/autor/categoria/data) e a seção "Mais populares",
# pronto para ser sobrescrito pelo workflow do catálogo.
set -euo pipefail

DOC="docs/community-packs.md"
FAIL=0

if [ ! -f "$DOC" ]; then
  echo "FAIL: $DOC não existe" >&2
  exit 1
fi

check() {
  local pattern="$1"
  local label="$2"
  if ! grep -qiF "$pattern" "$DOC"; then
    echo "FAIL: $DOC não contém $label" >&2
    FAIL=1
  fi
}

check "Link" "coluna Link"
check "Jogo" "coluna Jogo"
check "Console" "coluna Console"
check "Autor" "coluna Autor"
check "Categoria" "coluna Categoria"
check "Data" "coluna Data"
check "Mais populares" "a seção 'Mais populares'"
check "proxy de popularidade" "o rótulo de proxy de popularidade"

if [ "$FAIL" -ne 0 ]; then
  exit 1
fi

echo "PASS: AC-8 ($DOC tem header de tabela + seção Mais populares)"
