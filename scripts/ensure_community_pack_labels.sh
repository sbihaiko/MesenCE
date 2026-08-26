#!/usr/bin/env bash
# Garante (idempotente) a existência das labels usadas pelo fluxo de
# triagem de "Community HD/MEP Packs" (CLAUDE.md, seção "Triagem de
# Community HD/MEP Packs"). Rode uma vez ao configurar o repositório, ou
# de novo a qualquer momento — labels já existentes são ignoradas.
#
# Uso: scripts/ensure_community_pack_labels.sh
#
# Requer `gh` autenticado com acesso de escrita a issues/labels no repo.
set -euo pipefail

REPO="sbihaiko/MesenCE"

# name|color|description — '|' as separator because label names themselves
# contain ':' (e.g. "pack:invalid-structure").
LABELS=(
  "community-pack|1D76DB|Submissão de HD/MEP Pack da comunidade"
  "pack:invalid-structure|D93F0B|Falhou o lint estrutural (mep_lint.py)"
  "pack:invalid-license|D93F0B|Sem confirmação/direito de distribuição dos assets"
  "pack:invalid-other|D93F0B|Reprovado por outro motivo de conteúdo/política"
  "pack:partial-hd|FBCA04|Aceito parcial — apenas assets HD padrão Mesen"
  "pack:mep-full|0E8A16|Aceito — MEP completo (texturas + áudio/synth)"
)

for entry in "${LABELS[@]}"; do
  IFS='|' read -r name color description <<<"$entry"
  if gh label list --repo "$REPO" --json name -q '.[].name' | grep -qx "$name"; then
    echo "Já existe: $name"
  else
    gh label create "$name" --repo "$REPO" --color "$color" --description "$description"
    echo "Criada: $name"
  fi
done
