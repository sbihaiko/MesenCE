#!/usr/bin/env bash
# AC-10: CLAUDE.md keeps the original "Rastreamento de bugs (GitHub Project)"
# section byte-for-byte untouched and gains a new "Triagem de Community
# HD/MEP Packs (GitHub Project)" section documenting the second, separate
# board/flow. No mocks: this reads the real CLAUDE.md from the repo root.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLAUDE_MD="$REPO_ROOT/CLAUDE.md"

ORIG_HEADING="## Rastreamento de bugs (GitHub Project)"
NEW_HEADING="## Triagem de Community HD/MEP Packs (GitHub Project)"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[[ -f "$CLAUDE_MD" ]] || fail "CLAUDE.md não encontrado em $CLAUDE_MD"

# Exactly one occurrence of each heading: no duplication of the old section,
# and the new section must actually be present.
orig_count=$(grep -Fc "$ORIG_HEADING" "$CLAUDE_MD")
[[ "$orig_count" -eq 1 ]] || fail "esperava 1 ocorrência de '$ORIG_HEADING', achou $orig_count"

new_count=$(grep -Fc "$NEW_HEADING" "$CLAUDE_MD")
[[ "$new_count" -eq 1 ]] || fail "esperava 1 ocorrência de '$NEW_HEADING', achou $new_count"

# Byte-for-byte check: the original file content (title + bug-tracker
# section) must be an exact, untouched prefix of the current CLAUDE.md.
REF_FILE="$(mktemp)"
cleanup() { rm -f "$REF_FILE" "$ACTUAL_PREFIX"; }
trap cleanup EXIT

cat > "$REF_FILE" <<'EOF_REF'
# CLAUDE.md

## Rastreamento de bugs (GitHub Project)

Bugs deste projeto são registrados como GitHub Issues e acompanhados no board
"MesenCE Bug Tracker": https://github.com/users/sbihaiko/projects/1

### Quando registrar

- Você (ou um subagente do dev-squad) encontra um bug real, reproduzível, que
  está **fora do escopo da tarefa atual** — não conserte de passagem, registre.
- O usuário pede explicitamente para "abrir um bug" / "registrar uma issue".
- Não use isso para decisões de arquitetura/trade-offs — isso continua indo
  para ADR via `/dev-squad:adr` (`.dev-squad/adr/`). O board é só para bugs
  acionáveis, não para decisões de design.

### Como registrar

Use o helper `scripts/report-bug.sh` em vez de comandos `gh` manuais — ele já
seta o Status inicial ("To triage") e a Priority com os IDs corretos do board:

```bash
scripts/report-bug.sh "<título curto do bug>" "<descrição: repro, esperado vs observado>" [P0|P1|P2]
```

Isso cria a Issue no repo (label `bug`) e a adiciona ao board com Status =
"To triage". Requer `gh` autenticado com escopo `project`
(`gh auth refresh -h github.com -s project`, uma vez por máquina).

Campos do board disponíveis: Status (To triage → Todo → Doing → Testing →
Done), Priority (P0/P1/P2), Size (S/M/L). O script só seta Status e,
opcionalmente, Priority — mover para Todo/Doing/Done é manual (triagem
humana) ou feito pelo usuário no board.
EOF_REF

ref_len=$(wc -c < "$REF_FILE" | tr -d '[:space:]')
actual_len=$(wc -c < "$CLAUDE_MD" | tr -d '[:space:]')
[[ "$actual_len" -gt "$ref_len" ]] || fail "CLAUDE.md não cresceu — nova seção não foi anexada"

ACTUAL_PREFIX="$(mktemp)"
head -c "$ref_len" "$CLAUDE_MD" > "$ACTUAL_PREFIX"

cmp -s "$REF_FILE" "$ACTUAL_PREFIX" || {
  echo "--- diff (esperado vs. seção original atual) ---" >&2
  diff -u "$REF_FILE" "$ACTUAL_PREFIX" >&2 || true
  fail "a seção 'Rastreamento de bugs (GitHub Project)' foi alterada"
}

# The new heading must appear strictly after the untouched original block,
# i.e. it was appended, not spliced into the middle of the old section.
tail_from_ref_len="$(tail -c +"$((ref_len + 1))" "$CLAUDE_MD")"
grep -Fq "$NEW_HEADING" <<< "$tail_from_ref_len" \
  || fail "'$NEW_HEADING' não aparece depois da seção original preservada"

echo "PASS: CLAUDE.md mantém a seção de bugs intacta e contém a nova seção de triagem de packs"
