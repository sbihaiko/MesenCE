#!/usr/bin/env bash
# Verifica docs/hd-pack-authoring.md (AC-9): existe, não é trivial, e cita
# docs/specs/MEP-v1.md (as seções §5.1/§5.2/§5.3/§6 usadas nos veredictos
# de triagem de community packs).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOC="$REPO_ROOT/docs/hd-pack-authoring.md"

MIN_LINES=20

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$DOC" ] || fail "arquivo não encontrado: $DOC"

LINE_COUNT="$(wc -l < "$DOC" | tr -d ' ')"
if [ "$LINE_COUNT" -lt "$MIN_LINES" ]; then
  fail "$DOC tem só $LINE_COUNT linhas (esperado >= $MIN_LINES; parece trivial)"
fi

grep -q 'MEP-v1.md' "$DOC" || fail "$DOC não referencia MEP-v1.md"

for section in '§5.1' '§5.2' '§5.3' '§6'; do
  grep -qF "$section" "$DOC" || fail "$DOC não referencia a seção $section de MEP-v1.md"
done

echo "PASS: docs/hd-pack-authoring.md existe, não é trivial e referencia MEP-v1.md §5.1/§5.2/§5.3/§6"
