#!/usr/bin/env bash
#
# sync-upstream — pull upstream (nesdev-org/MesenCE) in by merge, never rebase
# (ADR-0163).
#
#  1. ensures rerere is on (rerere.enabled + rerere.autoUpdate), so the first
#     recorded resolution of each delete/modify conflict replays on later syncs;
#  2. fetches the upstream ref;
#  3. if the ref is already an ancestor of HEAD there is nothing to bring and the
#     script exits 0 (no-op);
#  4. otherwise it prints the *predicted* conflict sets for the commits upstream
#     is about to bring — delete/modify on tier-D files (resolution: keep the
#     fork's deletion) and modify/modify on tier-B files (needs a decision);
#  5. merges into the CURRENT branch. Run it on `main` locally. The scheduled
#     workflow (sync-upstream.yml) runs it on a sync/<date> branch and opens a
#     PR. When the merge stops on conflicts, delete/modify entries on tier-D
#     files are resolved automatically (git rm = keep the deletion) and the
#     merge is committed; any remaining conflict is a tier-B modify/modify and
#     is left for a human, with an error.
#
# Usage:
#   scripts/sync-upstream.sh [--ref upstream/master] [--no-merge]
#
#   --ref       upstream ref to fetch and merge (default: upstream/master)
#   --no-merge  fetch + print predictions only; never touch the index/worktree
#   -h, --help  this message
#
# Exit 0 on success/no-op; 1 when the merge needs a human decision, the ref
# cannot be resolved, or the merge cannot be committed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="upstream/master"
NO_MERGE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) REF="${2:?--ref needs a value}"; shift 2 ;;
    --no-merge) NO_MERGE=1; shift ;;
    -h|--help) sed -n '2,26p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

cd "$ROOT"

msg() { printf '\033[1m%s\033[0m\n' "$*"; }
die() { printf 'sync-upstream: %s\n' "$*" >&2; exit 1; }

# --- git identity is only needed if a resolution commit is produced ---
ensure_identity() {
  if ! git config user.email >/dev/null || ! git config user.name >/dev/null; then
    git config user.name "MesenCE sync"
    git config user.email "sync@mesence.local"
  fi
}

# --- 1. rerere is policy, not preference (ADR-0163) ---
git config rerere.enabled true
git config rerere.autoUpdate true

REMOTE="${REF%%/*}"
if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  die "no git remote '$REMOTE'. Add upstream first, e.g.: git remote add upstream https://github.com/nesdev-org/MesenCE"
fi
if ! git rev-parse --verify --quiet "$REF" >/dev/null; then
  die "cannot resolve ref '$REF' (fetch it first, or add remote '$REMOTE')"
fi

# --- 2. fetch ---
msg "fetching $REMOTE..."
git fetch "$REMOTE"

# --- 3. no-op when upstream has nothing new ---
if git merge-base --is-ancestor "$REF" HEAD; then
  msg "upstream ($REF) is already merged into HEAD — nothing to sync."
  exit 0
fi

# --- 4. predicted conflicts, from the live tiers ---
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
python3 scripts/upstream_tiers.py --json > "$TMP/snapshot.json"

count_field() { # $1 = predicted.<field>
  python3 -c 'import json,sys
d=json.load(open(sys.argv[1])).get("predicted") or {}
print(len(d.get(sys.argv[2], [])))' "$TMP/snapshot.json" "$1"
}
list_field() {
  python3 -c 'import json,sys
d=json.load(open(sys.argv[1])).get("predicted") or {}
print("\n".join(d.get(sys.argv[2], [])))' "$TMP/snapshot.json" "$1"
}

DM_COUNT="$(count_field delete_modify)"
MM_COUNT="$(count_field modify_modify)"
msg "merge will bring $(python3 -c 'import json,sys
print(json.load(open(sys.argv[1]))["behind"])' "$TMP/snapshot.json") upstream commit(s)."
msg "predicted delete/modify on tier-D files (auto-resolved: keep the fork's deletion): $DM_COUNT"
msg "predicted modify/modify on tier-B files (need a decision): $MM_COUNT"
list_field delete_modify | sed 's/^/  [D keep-deletion] /'
list_field modify_modify   | sed 's/^/  [B human-decision] /'

if [[ "$NO_MERGE" -eq 1 ]]; then
  msg "--no-merge: nothing touched. Run without it to merge."
  exit 0
fi

BRANCH="$(git branch --show-current)"
if [[ -n "$BRANCH" && "$BRANCH" != "main" && "${CI:-}" != "true" ]]; then
  msg "warning: merging into branch '$BRANCH' (not main). ADR-0163 merges on main;"
  msg "the scheduled workflow merges on a sync/<date> branch before opening a PR."
fi

# --- 5. merge; auto-resolve tier-D delete/modify ---
ensure_identity
if git merge --no-edit "$REF"; then
  msg "merge clean. upstream is now merged into $BRANCH."
  exit 0
fi

# merge stopped: resolve every unmerged path that is a tier-D delete/modify
# (ours deleted / theirs modified) by keeping our deletion.
# Bash 3.2 compatible (macOS system bash has no mapfile/readarray).
DELETED=()
while IFS= read -r line; do
  [[ -n "$line" ]] && DELETED+=("$line")
done < <(list_field delete_modify)
UNMERGED=()
while IFS= read -r line; do
  [[ -n "$line" ]] && UNMERGED+=("$line")
done < <(git diff --name-only --diff-filter=U || true)
RESOLVED=0
for path in "${UNMERGED[@]:-}"; do
  for del in "${DELETED[@]:-}"; do
    if [[ "$path" == "$del" ]]; then
      git rm -f -- "$path" >/dev/null
      RESOLVED=$((RESOLVED + 1))
      break
    fi
  done
done
msg "auto-resolved $RESOLVED delete/modify conflict(s) on tier-D files (kept deletion)."

REMAINING="$(git diff --name-only --diff-filter=U || true)"
if [[ -n "$REMAINING" ]]; then
  echo "$REMAINING" | sed 's/^/  remaining conflict: /' >&2
  die "unresolved tier-B (modify/modify) conflicts above need a decision. Resolve them, then finish with: git commit --no-edit (ADR-0163: do not restore tier-D deletions)"
fi

git commit --no-edit
msg "merge committed. upstream is now merged into $BRANCH."
