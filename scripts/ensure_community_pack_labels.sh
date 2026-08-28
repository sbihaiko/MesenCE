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
# contain ':' (e.g. "pack:invalid").
LABELS=(
  "community-pack|1D76DB|Community-submitted HD/MEP Pack"
  "pack:valid|0E8A16|Accepted — has at least one usable MEP-v1 §5 section (textures/audio/synth)"
  "pack:invalid|D93F0B|Rejected — no usable section content, or another content/policy problem"
  "assets:textures|FBCA04|Pack declares <img>/<tile>/<background> (graphics) content"
  "assets:audio|FBCA04|Pack declares <bgm>/<sfx> (audio) content"
  "patch:ips|2D4F8F|Pack bundles an IPS-format ROM patch"
  "patch:bps|2D4F8F|Pack bundles a BPS-format ROM patch"
  "console:nes|5319E7|Pack targets the NES console"
  "console:gb|5319E7|Pack targets the GB/GBC console"
  "console:gbc|5319E7|Pack targets the GB/GBC console"
  "console:sms|5319E7|Pack targets the SMS/GG/SG-1000 console"
  "assets:external|FBCA04|Pack declares external_assets (split-distribution content-index) dependencies"
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
