#!/usr/bin/env bash
# Files a bug as a GitHub Issue and adds it to the "MesenCE Bug Tracker" board
# (github.com/users/sbihaiko/projects/1), already with Status = "To triage".
#
# Usage: scripts/report-bug.sh "<title>" "<body>" [P0|P1|P2]
#
# Requires `gh` authenticated with the `project` scope (gh auth refresh -s project).
set -euo pipefail

REPO="sbihaiko/MesenCE"
OWNER="sbihaiko"
PROJECT_NUMBER=1
PROJECT_ID="PVT_kwHOB1MsbM4BhjX3"
STATUS_FIELD_ID="PVTSSF_lAHOB1MsbM4BhjX3zhgesr0"
STATUS_TRIAGE_OPTION_ID="f971fb55"
PRIORITY_FIELD_ID="PVTSSF_lAHOB1MsbM4BhjX3zhges5M"

usage() {
  echo "Usage: $0 <title> <body> [P0|P1|P2]" >&2
  exit 1
}

[ $# -ge 2 ] || usage
TITLE="$1"
BODY="$2"
PRIORITY="${3:-}"

case "$PRIORITY" in
  ""|P0|P1|P2) ;;
  *) echo "Invalid priority: $PRIORITY (use P0, P1, or P2)" >&2; exit 1 ;;
esac

ISSUE_URL=$(gh issue create --repo "$REPO" --title "$TITLE" --body "$BODY" --label bug)
echo "Issue created: $ISSUE_URL"

ITEM_ID=$(gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "$ISSUE_URL" --format json -q '.id')

gh project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
  --field-id "$STATUS_FIELD_ID" --single-select-option-id "$STATUS_TRIAGE_OPTION_ID" >/dev/null

if [ -n "$PRIORITY" ]; then
  case "$PRIORITY" in
    P0) OPT_ID="79628723" ;;
    P1) OPT_ID="0a877460" ;;
    P2) OPT_ID="da944a9c" ;;
  esac
  gh project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
    --field-id "$PRIORITY_FIELD_ID" --single-select-option-id "$OPT_ID" >/dev/null
fi

echo "Added to board: https://github.com/users/$OWNER/projects/$PROJECT_NUMBER"
