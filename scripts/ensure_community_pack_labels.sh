#!/usr/bin/env bash
# Idempotently ensures the labels used by the "Community HD/MEP Packs"
# triage flow exist (CLAUDE.md, "Community HD/MEP Pack triage" section).
# Run once when setting up the repository, or again at any time — labels
# that already exist are skipped.
#
# Usage: scripts/ensure_community_pack_labels.sh
#
# Requires `gh` authenticated with write access to issues/labels on the repo.
set -euo pipefail

REPO="sbihaiko/MesenCE"

# name|color|description — '|' as separator because label names themselves
# contain ':' (e.g. "pack:invalid-structure").
LABELS=(
  "community-pack|1D76DB|Community-submitted HD/MEP Pack"
  "pack:invalid-structure|D93F0B|Failed the structural lint (mep_lint.py)"
  "pack:invalid-license|D93F0B|Missing confirmation/right to distribute the assets"
  "pack:invalid-other|D93F0B|Rejected for another content/policy reason"
  "pack:partial-hd|FBCA04|Partially accepted — standard Mesen HD assets only"
  "pack:mep-full|0E8A16|Accepted — full MEP (textures + audio/synth)"
  "asset:textures|5319E7|Pack declares <img>/<tile>/<background> (graphics) content"
  "asset:audio|5319E7|Pack declares <bgm>/<sfx> (audio) content"
  "asset:ips|5319E7|Pack bundles an IPS-format ROM patch"
  "asset:bps|5319E7|Pack bundles a BPS-format ROM patch"
)

for entry in "${LABELS[@]}"; do
  IFS='|' read -r name color description <<<"$entry"
  if gh label list --repo "$REPO" --json name -q '.[].name' | grep -qx "$name"; then
    echo "Already exists: $name"
  else
    gh label create "$name" --repo "$REPO" --color "$color" --description "$description"
    echo "Created: $name"
  fi
done
