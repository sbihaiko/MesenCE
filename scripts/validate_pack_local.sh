#!/usr/bin/env bash
# Local equivalent of community-pack-validate.yml's classify pipeline
# (F6.5). Fetches a community pack from its issue, lints it, runs the
# classify prompt from .github/ai/validate-classify.md through Claude, then
# deterministically assembles/validates the MEP recipe (when external assets
# are declared) and records state on the issue — comment, labels, Project
# Status/Category/Pack Hash, and the `<!-- mep-meta -->` comment.
#
# ADR-0143: a submission whose zip contains N game packs (N subfolder pack
# roots, or one pack.json per game) is SPLIT by the pipeline into N packs and
# N sibling issues. The contributor opens one issue; this script detects the
# multi-game container via `mep_lint.py --list-games`, creates the N-1 sibling
# issues automatically with `gh`, then runs the whole per-game pipeline once
# per game against a game-scoped copy of the zip. Each game's mep-meta records
# `game`, `content_id`, `pack_id` (origin x game, ADR-0143) and `siblings[]`.
#
# The .md prompt is the single source: the CI workflow renders and runs the
# same file, so a pack triaged here and one triaged there are judged against
# identical instructions.
#
# Usage:
#   scripts/validate_pack_local.sh <issue-number> [options]
#
# Options:
#   --llm claude|session   How to run the classify step (default: claude).
#                            claude  — invoke the `claude` CLI headless with the
#                                      rendered prompt (what the CI does).
#                            session — render the prompt to <work>/classify_prompt.md
#                                      and use <work>/classify_raw.json if present;
#                                      otherwise print instructions and exit.
#   --model <model>        Model for the headless classify (default: claude-sonnet-4-5;
#                          the session model is invalid for `claude -p`).
#   --no-write             Do not write anything to the issue/board; only prepare
#                          and run the steps, printing what would be applied.
#   --no-comment           Apply labels/board/mep-meta but skip posting the verdict
#                          comment (idempotent re-runs).
#   --parallel             In a multi-game split, validate the games concurrently
#                          (each in its own subshell/work dir) instead of one after
#                          another. Only affects SPLIT runs.
#   --work <dir>           Work directory override (default: .cache/validate-local/<issue>).
#                          In a multi-game split, each game uses its own
#                          <work>/<game-issue> subdirectory.
#
# Requires `gh` authenticated with `project` scope (Project v2 writes).
set -euo pipefail

# ---- board / project constants (mirror community-pack-validate.yml env) ----
REPO="sbihaiko/MesenCE"
OWNER="sbihaiko"
PROJECT_NUMBER=3
PROJECT_ID="PVT_kwHOB1MsbM4BhjpN"
STATUS_FIELD_ID="PVTSSF_lAHOB1MsbM4BhjpNzhge86c"
STATUS_NOVO_ENVIO="5173b5cd"
STATUS_EM_VALIDACAO="51951f52"
STATUS_INVALIDO="227e4623"
STATUS_ACEITO_PARCIAL="39e4f3a1"
STATUS_ACEITO_COMPLETO="cd763737"
PACK_HASH_FIELD_ID="PVTF_lAHOB1MsbM4BhjpNzhge9Is"
GAME_FIELD_ID="PVTF_lAHOB1MsbM4BhjpNzhghmoA"
CONSOLE_FIELD_ID="PVTSSF_lAHOB1MsbM4BhjpNzhghmoE"
CONSOLE_NES="ceb4bb8a"
CONSOLE_GB="74fea5ea"
CONSOLE_GBC="0f2858ab"
CONSOLE_SMS="c4bc3f87"
CONSOLE_OTHER="e810a7e3"
CATEGORY_FIELD_ID="PVTSSF_lAHOB1MsbM4BhjpNzhghmpY"
CATEGORY_FULL_MEP="512e4e17"
CATEGORY_PARTIAL_HD="d9566561"
PACK_URL_FIELD_ID="PVTF_lAHOB1MsbM4BhjpNzhghmqU"
PACK_MD5_FIELD_ID="PVTF_lAHOB1MsbM4BhjpNzhghmrQ"
ROM_SHA1_FIELD_ID="PVTF_lAHOB1MsbM4BhjpNzhghmrU"
ROM_MD5_FIELD_ID="PVTF_lAHOB1MsbM4BhjpNzhghmrY"
MAX_PACK_BYTES=314572800
PROMPT_FILE=".github/ai/validate-classify.md"

# ---- parse args ----
ISSUE=""
LLM="claude"
MODEL=""
NO_WRITE=0
NO_COMMENT=0
PARALLEL=0
WORK=""
PREPARE_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --llm=*) LLM="${1#--llm=}" ;;
    --llm) LLM="$2"; shift ;;
    --model=*) MODEL="${1#--model=}" ;;
    --model) MODEL="$2"; shift ;;
    --work=*) WORK="${1#--work=}" ;;
    --work) WORK="$2"; shift ;;
    --no-write) NO_WRITE=1 ;;
    --no-comment) NO_COMMENT=1 ;;
    --parallel) PARALLEL=1 ;;
    -h|--help)
      sed -n '2,34p' "$0"
      exit 0
      ;;
    *) ISSUE="$1" ;;
  esac
  shift
done

if [ -z "$ISSUE" ]; then
  echo "error: issue number required" >&2
  sed -n '2,34p' "$0" >&2
  exit 1
fi
case "$LLM" in claude|session) ;; *) echo "error: --llm must be claude or session" >&2; exit 1 ;; esac

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# The primary issue's work dir; each game in a split gets its own
# <work>/<game-issue> subdirectory (see run_game).
WORK_BASE="${WORK:-.cache/validate-local/$ISSUE}"
# In supervised-prepare mode (--llm session with no classify output yet) the
# run is a dry prep: a lint failure must be REPORTED, not written to the
# issue/board — the apply path only runs once the classify step is real.
if [ "$LLM" = "session" ] && [ ! -f "$WORK_BASE/classify_raw.json" ]; then
  PREPARE_ONLY=1
fi
# macOS Python.org builds don't ship a default CA bundle, so urllib (used by
# fetch_pack.py) fails TLS verification locally. Point at certifi when present;
# CI runners ship system certs and are unaffected.
if python3 -c "import certifi" 2>/dev/null; then
  export SSL_CERT_FILE="$(python3 -c 'import certifi; print(certifi.where())')"
fi
mkdir -p "$WORK_BASE"
echo "work=$WORK_BASE"
# Ensure the triage labels exist (pack:split included) before anything that
# writes to issues runs — sibling-issue creation needs pack:split right away.
if [ "$NO_WRITE" -eq 0 ]; then
  bash scripts/ensure_community_pack_labels.sh >/dev/null
fi

# ---- 1. read the issue ----
BODY=$(gh issue view "$ISSUE" --repo "$REPO" --json body -q '.body')
printf '%s' "$BODY" > "$WORK_BASE/issue_body.txt"

GAME=$(python3 -c "import re, sys; body = sys.stdin.read(); m = re.search(r'^###\s+Target game/ROM and region\s*\n+(.*?)(?=\n###\s|\Z)', body, re.M | re.S); value = (m.group(1).strip() if m else '').splitlines(); print(value[0].strip() if value else '')" <<<"$BODY")
echo "game=$GAME"

# Console is submitter-declared Issue Form metadata, used for the board's
# Console field (recorded in apply) and for the console:* label on the issue
# itself (mirrors community-pack-validate.yml's "Record submission metadata").
CONSOLE=$(python3 -c "import re, sys; body = sys.stdin.read(); m = re.search(r'^###\s+Console\s*\n+(.*?)(?=\n###\s|\Z)', body, re.M | re.S); value = (m.group(1).strip() if m else '').splitlines(); print(value[0].strip() if value else '')" <<<"$BODY")
echo "console=$CONSOLE"

PACK_URL=$(printf '%s' "$BODY" | grep -oE 'https://[^ )]+' | head -n1 || true)
if [ -z "$PACK_URL" ]; then
  echo "error: no pack URL found in the issue body" >&2
  exit 1
fi
echo "pack_url=$PACK_URL"

# ---- 2. host allow-list + download ----
if ! python3 -c "
import sys
sys.path.insert(0, 'scripts')
from fetch_pack import match_host, load_allowlist
hosts = load_allowlist('scripts/pack_host_allowlist.json')
sys.exit(0 if match_host(sys.argv[1], hosts) else 1)
" "$PACK_URL" 2>/dev/null; then
  echo "error: host not in scripts/pack_host_allowlist.json" >&2
  exit 1
fi
python3 scripts/fetch_pack.py "$PACK_URL" "$WORK_BASE/pack_download.bin" \
  --max-bytes "$MAX_PACK_BYTES" --allowlist scripts/pack_host_allowlist.json
PACK_SHA256=$(sha256sum "$WORK_BASE/pack_download.bin" | awk '{print $1}')
PACK_MD5=$(md5sum "$WORK_BASE/pack_download.bin" | awk '{print $1}')
echo "sha256=$PACK_SHA256"
echo "md5=$PACK_MD5"

# ---- 3. resolve game roots (ADR-0143) ----
# A container holding N subfolder packs (or one pack.json per game) is split
# into N games and N issues; a single pack keeps the existing one-issue flow.
GAME_MAP="$WORK_BASE/games.tsv"
if python3 scripts/mep_lint.py --list-games "$WORK_BASE/pack_download.bin" > "$GAME_MAP" 2>/dev/null; then
  GAME_ROOTS=(); GAME_NAMES=()
  while IFS=$'\t' read -r r g; do
    [ -z "$r" ] && [ -z "$g" ] && continue
    GAME_ROOTS+=("$r"); GAME_NAMES+=("$g")
  done < "$GAME_MAP"
fi
GAME_COUNT=${#GAME_ROOTS[@]}
SPLIT=0
if [ "$GAME_COUNT" -eq 0 ]; then
  # No recognizable pack root (--list-games empty): keep the single-game flow
  # so the existing "no section found" lint rejection, anchored on the Issue
  # Form's game name, fires exactly as before.
  GAME_COUNT=1; GAME_ROOTS=(""); GAME_NAMES=("$GAME")
elif [ "$GAME_COUNT" -eq 1 ] && [ -z "${GAME_ROOTS[0]}" ]; then
  # A single pack at the container root: keep the submitter-declared game
  # name (what the board Game field and the catalog row show today).
  GAME_NAMES[0]="$GAME"
fi
if [ "$GAME_COUNT" -gt 1 ]; then
  SPLIT=1
  echo ":: multi-game container detected ($GAME_COUNT game packs) — splitting into one issue per game (ADR-0143)"
  for ((i=0; i<GAME_COUNT; i++)); do
    echo "  game[$i] root='${GAME_ROOTS[$i]}' name='${GAME_NAMES[$i]}'"
  done
fi

# ---- 4. split: create sibling issues + per-game zips ----
SIB_ISSUES=()
if [ "$SPLIT" -eq 1 ]; then
  FULL_ZIP="$WORK_BASE/pack_download.bin"
  # Save the full container so each per-game zip below is built from it, not
  # from game 0's freshly-written per-game copy.
  cp "$FULL_ZIP" "$WORK_BASE/split_source.bin"
  if [ "$NO_WRITE" -eq 0 ]; then
    # Re-validation (idempotent, /revalidate flow): a submission already split
    # records its sibling issues on the primary's mep-meta siblings[] — reuse
    # them instead of minting duplicates. Only reused when the count matches
    # this run's game count; otherwise create fresh siblings.
    EXISTING_SIBLINGS=""
    EXISTING_SIBLINGS=$(gh api "repos/$REPO/issues/$ISSUE/comments" --paginate \
      --jq ".[] | select((.user.login == \"$OWNER\") and (.body | test(\"<!-- mep-meta -->\"))) | .body" 2>/dev/null \
      | python3 -c "import sys,re,json; b=sys.stdin.read(); m=re.search(r'\`\`\`json\n(.*?)\n\`\`\`', b, re.S); d=json.loads(m.group(1)) if m else {}; s=d.get('siblings') or []; print(' '.join(str(x) for x in s))" || true)
    # `grep` exits 1 on no match, which under `set -euo pipefail` would kill
    # the run before `wc` even ran — a fresh split (no prior mep-meta) has an
    # empty EXISTING_SIBLINGS, so the pipeline must tolerate that and count 0.
    EXISTING_COUNT=$(echo -n "$EXISTING_SIBLINGS" | grep -oE '[0-9]+' | wc -l | tr -d ' ' || true)
    if [ "$EXISTING_COUNT" -eq $((GAME_COUNT - 1)) ]; then
      read -r -a SIB_ISSUES <<< "$EXISTING_SIBLINGS"
      echo ":: reusing existing sibling issues: ${SIB_ISSUES[*]} (re-validation)"
    else
      for ((i=1; i<GAME_COUNT; i++)); do
        g="${GAME_NAMES[$i]}"
        SIB_BODY=$(cat <<EOF
This is an automated sibling issue of #$ISSUE — the pipeline split a single community-pack submission whose zip contains $GAME_COUNT game packs into one issue per game, so each pack keeps its own identity and catalog slot (ADR-0143). No action is needed on this issue; the original submission is #$ISSUE, and the validation verdict for this game is posted below, same as the original.

### Target game/ROM and region

$g

### Console

$CONSOLE
EOF
)
        SIB_N=$(gh issue create --repo "$REPO" --title "[Pack] $g" \
          --label "community-pack" --label "pack:split" --body "$SIB_BODY" | grep -oE '[0-9]+$' || true)
        if [ -z "$SIB_N" ]; then
          echo "error: failed to create sibling issue for '$g'" >&2
          exit 1
        fi
        SIB_ISSUES+=("$SIB_N")
        echo ":: sibling issue #$SIB_N created for game '$g'"
      done
    fi
    # The primary issue is game 0 of the split: retitle it to the real game
    # and mark it as a split participant.
    gh issue edit "$ISSUE" --repo "$REPO" --title "[Pack] ${GAME_NAMES[0]}" --add-label "pack:split"
  fi
  # Build one game-scoped zip per game (its root stripped), so every game's
  # per-game pipeline (lint / content-id / classify) sees exactly one pack.
  for ((i=0; i<GAME_COUNT; i++)); do
    if [ "$NO_WRITE" -eq 1 ]; then
      GW="$WORK_BASE-g$i"
    elif [ "$i" -eq 0 ]; then
      GW="$WORK_BASE"
    else
      GW=".cache/validate-local/${SIB_ISSUES[$((i-1))]}"
    fi
    mkdir -p "$GW"
    python3 - "$WORK_BASE/split_source.bin" "${GAME_ROOTS[$i]}" "$GW/pack_download.bin" <<'PY'
import sys
import zipfile
from pathlib import Path
sys.path.insert(0, 'scripts')
from mep_lint import Source, safe_rel
src = Source(Path(sys.argv[1]))
prefix = sys.argv[2]
out = sys.argv[3]
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    # A game root may be a whole subfolder (prefix '<dir>/' semantics: copy
    # every file under it, stripping the prefix) OR a single nested .zip
    # (ADR-0143 repo-archive shape: find_nested_game_zips returns the exact
    # zip path, so copy just that one file — a subfolder holding several
    # valid variant zips must not leak all of them into the per-game zip,
    # which would trip the exactly-one-top-level-zip fallback).
    is_zip_root = prefix.lower().endswith('.zip')
    for name in sorted(src.names):
        rel = safe_rel(name)
        if rel is None:
            continue
        if is_zip_root:
            if rel != prefix:
                continue
            inner = rel.rsplit('/', 1)[-1]
        else:
            if prefix and not rel.startswith(prefix + '/'):
                continue
            inner = rel[len(prefix) + 1:] if prefix else rel
        if not inner or inner.endswith('/'):
            continue
        z.writestr(inner, src.read(name))
PY
    echo ":: game[$i] zip built -> $GW/pack_download.bin (root '${GAME_ROOTS[$i]}')"
  done
fi

# ---- per-game pipeline (lint -> content-id -> classify -> recipe -> apply -> mep-meta) ----
# $1 issue  $2 game  $3 root (informational; baked into the game zip)  $4 siblings csv  $5 work dir
run_game() {
  local ISSUE="$1" GAME="$2" ROOT="$3" SIBLINGS_CSV="$4" WORK="$5"
  local CONTENT_ID="" LINT_EXIT RECIPE_STATUS RECIPE_OK VERDICT DOWNGRADED CATEGORY KIND
  local APPLIED_LABELS LABEL ITEM_ID

  # The recipe assembly reads the External assets section, which only the
  # primary issue declares (a split's submission-level data) — carry the
  # primary body into every game's work dir so assemble-sources sees it.
  printf '%s' "$BODY" > "$WORK/issue_body.txt"

  # ---- 5. lint ----
  set +e
  python3 scripts/mep_lint.py "$WORK/pack_download.bin" "$GAME" --quiet > "$WORK/mep_lint_output.txt" 2>&1
  LINT_EXIT=$?
  set -e
  echo "lint_exit=$LINT_EXIT ($(tail -1 "$WORK/mep_lint_output.txt"))"
  if [ "$LINT_EXIT" -ne 0 ]; then
    echo ":: lint failed — pack rejected by mep_lint.py (see $WORK/mep_lint_output.txt)"
    if [ "$NO_WRITE" -eq 0 ] && [ "$PREPARE_ONLY" -eq 0 ]; then
      {
        echo ""
        echo "Pack SHA-256: \`$PACK_SHA256\` — pin this against the pack link; a link that starts serving a different file changes this hash, and this verdict is stale until \`/revalidate\` runs again."
      } >> "$WORK/mep_lint_output.txt"
      gh issue comment "$ISSUE" --repo "$REPO" --body-file "$WORK/mep_lint_output.txt"
      gh issue edit "$ISSUE" --repo "$REPO" --add-label pack:invalid
      ITEM_ID=$(gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "https://github.com/$REPO/issues/$ISSUE" --format json -q '.id')
      gh project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
        --field-id "$STATUS_FIELD_ID" --single-select-option-id "$STATUS_INVALIDO" >/dev/null
      echo ":: recorded rejection on issue #$ISSUE"
    fi
    return 0
  fi

  # ---- 6. content_id (ADR-0139/P.1) ----
  if python3 scripts/mep_lint.py --content-id "$WORK/pack_download.bin" > "$WORK/content_id.txt" 2>&1; then
    CONTENT_ID=$(cat "$WORK/content_id.txt")
  fi
  echo "content_id=$CONTENT_ID"

  # ---- 7. render the classify prompt from the .md ----
  EXT="$(printf '%s' "$BODY" | sed -n '/^### *External assets/I,$p' | sed '1d' | sed '/^### /,$d' | sed '/^[[:space:]]*$/d' || true)"
  if [ -n "$EXT" ]; then
    SUFFIX="THE SUBMISSION DECLARES EXTERNAL ASSETS (MEP-recipe-v1 §3.3, user_supplied deps hosted separately) — this is the ADR-0138 §2/§7 EXCEPTION: the referenced section counts as usable, verdict MUST be \"accepted\", and the recipe object MUST be filled (deps user_supplied, no sha256/size). Do not apply MEP-v1 §5's missing-file rule to these:
    $(printf '%s' "$EXT" | sed 's/^/  - /')"
  else
    SUFFIX=""
  fi

  python3 - "$PROMPT_FILE" "$ISSUE" "$SUFFIX" "$WORK" "$ROOT" <<'PY'
import os
import subprocess
import sys

path, issue, suffix, work, root = sys.argv[1:6]
brief = subprocess.check_output(
    [
        sys.executable,
        os.path.join(root, "scripts/classify_pack_brief.py"),
        os.path.join(work, "pack_download.bin"),
        os.path.join(work, "mep_lint_output.txt"),
    ],
    text=True,
    cwd=root,
)
text = open(path, encoding="utf-8").read()
# rsplit: the markers also appear in prose (the "<!-- SCHEMA -->" mention in
# the doc header), so split on the LAST occurrence — the real delimiters.
prompt = text.rsplit("<!-- PROMPT -->", 1)[1].rsplit("<!-- SCHEMA -->", 1)[0].strip()
schema = text.rsplit("<!-- SCHEMA -->", 1)[1].strip()
prompt = (
    prompt.replace("{{ISSUE_NUMBER}}", issue)
    .replace("{{EXTERNAL_ASSETS_SUFFIX}}", suffix)
    .replace("{{PACK_BRIEF}}", brief)
)
with open(os.path.join(work, "classify_prompt.md"), "w", encoding="utf-8") as f:
    f.write(prompt + "\n")
with open(os.path.join(work, "classify_schema.json"), "w", encoding="utf-8") as f:
    f.write(schema + "\n")
PY
  echo "prompt rendered -> $WORK/classify_prompt.md"

  # ---- 8. run classify ----
  SCHEMA=$(cat "$WORK/classify_schema.json")
  if [ "$LLM" = "claude" ]; then
    MODEL="${MODEL:-claude-sonnet-4-5}"
    echo ":: running claude headless (--llm claude, model $MODEL)..."
    # Evidence is already in classify_prompt.md as PACK BRIEF — do not
    # allow Read of pack_download.bin / hires.txt (issue #148 timeout).
    # The prompt goes via stdin. --output-format text keeps classify_raw.json
    # to just the model's JSON. --mcp-config {} drops MCP servers from the
    # system prompt (~119k input tokens otherwise).
    ( cd "$WORK" && ln -sfn "$ROOT/docs" docs && claude -p \
      --output-format text --json-schema "$SCHEMA" \
      --mcp-config '{"mcpServers":{}}' --disallowedTools "Bash,Read" \
      --model "$MODEL" < classify_prompt.md > classify_raw.json )
  elif [ -f "$WORK/classify_raw.json" ]; then
    echo ":: using existing $WORK/classify_raw.json"
  else
    echo ":: --llm session — classify prompt rendered to:"
    echo "   $WORK/classify_prompt.md"
    echo "   Read it (the PACK BRIEF is already inlined; do not open the zip),"
    echo "   produce the JSON per the schema in $WORK/classify_schema.json,"
    echo "   save it to $WORK/classify_raw.json, then re-run this script."
    return 0
  fi

  # ---- 9. sanitize classify JSON (repair real newlines inside strings) ----
  python3 - "$WORK/classify_raw.json" > "$WORK/classify_clean.json" <<'PY'
import sys, json
with open(sys.argv[1]) as _f:
    raw = _f.read()
try:
    json.loads(raw)
    sys.stdout.write(raw)
    sys.exit(0)
except json.JSONDecodeError:
    pass
out = []
in_str = False
i = 0
n = len(raw)
while i < n:
    c = raw[i]
    if in_str:
        if c == '\\' and i + 1 < n:
            out.append(c); out.append(raw[i + 1]); i += 2; continue
        if c == '"':
            in_str = False
        elif c == '\n':
            out.append('\\n'); i += 1; continue
        out.append(c); i += 1
    else:
        if c == '"':
            in_str = True
        out.append(c); i += 1
fixed = ''.join(out)
json.loads(fixed)
sys.stdout.write(fixed)
PY
  echo "verdict=$(jq -r '.verdict' "$WORK/classify_clean.json")"
  echo "assets=$(jq -r '.assets | join(",")' "$WORK/classify_clean.json")"
  echo "author=$(jq -r '.author' "$WORK/classify_clean.json")"

  # ---- 10. assemble + gate the MEP recipe (deterministic) ----
  ASSEMBLE_OUTPUT=$(python3 scripts/mep_recipe.py assemble-sources \
    --issue-body "$WORK/issue_body.txt" \
    --classify <(jq -r '.recipe // {}' "$WORK/classify_clean.json") \
    --pack-url "$PACK_URL" \
    --pack-sha256 "$PACK_SHA256" \
    --out "$WORK/mep_recipe.json")
  RECIPE_STATUS="${ASSEMBLE_OUTPUT#recipe_status: }"
  echo "recipe_status=$RECIPE_STATUS"
  RECIPE_OK=""
  if [ "$RECIPE_STATUS" = "present" ]; then
    RECIPE_OK=true
    if ! python3 scripts/mep_recipe.py validate "$WORK/mep_recipe.json"; then
      RECIPE_OK=false
    fi
    if [ "$RECIPE_OK" = "true" ]; then
      DRY_RUN_OUT="$WORK/mep_recipe_dry_run"
      rm -rf "$DRY_RUN_OUT"
      if [ -n "$GAME" ]; then
        python3 scripts/mep_recipe.py dry-run "$WORK/mep_recipe.json" \
          --primary "$WORK/pack_download.bin" --out "$DRY_RUN_OUT" --rom-name "$GAME" || RECIPE_OK=false
      else
        python3 scripts/mep_recipe.py dry-run "$WORK/mep_recipe.json" \
          --primary "$WORK/pack_download.bin" --out "$DRY_RUN_OUT" || RECIPE_OK=false
      fi
    fi
    echo "recipe_ok=$RECIPE_OK"
  fi

  # ---- 11. apply verdict (deterministic writer) ----
  VERDICT=$(jq -r '.verdict' "$WORK/classify_clean.json")
  DOWNGRADED=false
  if [ "$VERDICT" = "accepted" ] && [ "$RECIPE_STATUS" = "present" ] && [ "$RECIPE_OK" != "true" ]; then
    VERDICT="invalid"
    DOWNGRADED=true
  fi
  jq -r '.comment' "$WORK/classify_clean.json" > "$WORK/verdict_comment.txt"
  {
    echo ""
    echo "---"
    echo ""
    echo "<details><summary>Lint report (<code>scripts/mep_lint.py</code>)</summary>"
    echo ""
    echo '```'
    cat "$WORK/mep_lint_output.txt"
    echo '```'
    echo "</details>"
    echo ""
    echo "Pack SHA-256: \`$PACK_SHA256\` — pin this against the pack link; a link that starts serving a different file changes this hash, and this verdict is stale until \`/revalidate\` runs again."
  } >> "$WORK/verdict_comment.txt"
  if [ "$DOWNGRADED" = "true" ]; then
    {
      echo ""
      echo "Downgraded from \`accepted\` to \`invalid\`: the assembled MEP recipe (external-asset re-packaging, ADR-0138) failed \`mep_recipe.py validate\`/\`dry-run\`. See [MEP-recipe-v1.md](https://github.com/$REPO/blob/main/docs/specs/MEP-recipe-v1.md)."
    } >> "$WORK/verdict_comment.txt"
  fi
  if [ "$RECIPE_STATUS" = "refused" ]; then
    {
      echo ""
      echo "External assets were **not** turned into a MEP recipe: at least one \`External assets\` line is malformed or lacks its sha256. Each line must be \`<url> <sha256> [<size>]\` — compute the digest with \`sha256sum <file>\`, edit the issue, and comment \`/revalidate\`. See [MEP-recipe-v1.md](https://github.com/$REPO/blob/main/docs/specs/MEP-recipe-v1.md)."
    } >> "$WORK/verdict_comment.txt"
  fi

  CATEGORY=""
  case "$VERDICT" in
    accepted) FINAL="$STATUS_ACEITO_PARCIAL"; CATEGORY="$CATEGORY_PARTIAL_HD"; LABEL="pack:valid" ;;
    invalid) FINAL="$STATUS_INVALIDO"; LABEL="pack:invalid" ;;
    *) echo "error: unrecognized verdict '$VERDICT'" >&2; exit 1 ;;
  esac
  KIND=""
  case "$CATEGORY" in
    "$CATEGORY_FULL_MEP") KIND="mep" ;;
    "$CATEGORY_PARTIAL_HD") KIND="hd-legacy" ;;
  esac

  echo "== apply (issue #$ISSUE, game=$GAME, verdict=$VERDICT, label=$LABEL, kind=$KIND, downgraded=$DOWNGRADED) =="
  if [ "$NO_WRITE" -eq 1 ]; then
    echo ":: --no-write — not posting comment/labels/board/mep-meta. Draft comment:"
    cat "$WORK/verdict_comment.txt"
    return 0
  fi
  # Idempotent — creates any missing community-pack labels (assets:external
  # included) so the per-asset label loop below never fails mid-apply.
  bash scripts/ensure_community_pack_labels.sh >/dev/null
  if [ "$NO_COMMENT" -eq 0 ]; then
    gh issue comment "$ISSUE" --repo "$REPO" --body-file "$WORK/verdict_comment.txt"
  else
    echo ":: --no-comment — skipping verdict comment (labels/board/mep-meta only)"
  fi
  gh issue edit "$ISSUE" --repo "$REPO" --add-label "$LABEL"
  # Remove the opposite verdict label so the issue never carries both
  # pack:valid and pack:invalid (a prior CI run may have left one behind).
  OPPOSITE_LABEL=""
  [ "$LABEL" = "pack:valid" ] && OPPOSITE_LABEL="pack:invalid"
  [ "$LABEL" = "pack:invalid" ] && OPPOSITE_LABEL="pack:valid"
  if [ -n "$OPPOSITE_LABEL" ]; then
    gh issue edit "$ISSUE" --repo "$REPO" --remove-label "$OPPOSITE_LABEL" || true
  fi
  APPLIED_LABELS="$LABEL"

  # Console label (console:nes/gb/gbc/sms) mirrors the board's Console field so
  # the console is visible directly on the issue. No console:snes — SNES is not
  # a product console on main (docs/roadmap/AGENTS.md). "Other" is accepted on
  # the board but gets no label.
  if [ -n "${CONSOLE:-}" ]; then
    case "$CONSOLE" in
      NES|GB|GBC|SMS)
        L="console:$(echo "$CONSOLE" | tr 'A-Z' 'a-z')"
        gh issue edit "$ISSUE" --repo "$REPO" --add-label "$L"
        APPLIED_LABELS="$APPLIED_LABELS $L"
        ;;
    esac
  fi

  HAS_EXTERNAL_DEPS=""
  if [ "$RECIPE_STATUS" = "present" ]; then
    DEPS_COUNT=$(jq -r '(.sources.deps // []) | length' "$WORK/mep_recipe.json")
    [ "$DEPS_COUNT" != "0" ] && HAS_EXTERNAL_DEPS=1
  fi
  while IFS= read -r asset; do
    [ -z "$asset" ] && continue
    case "$asset" in
      textures|audio) L="assets:$asset"; gh issue edit "$ISSUE" --repo "$REPO" --add-label "$L"; APPLIED_LABELS="$APPLIED_LABELS $L" ;;
      ips|bps) L="patch:$asset"; gh issue edit "$ISSUE" --repo "$REPO" --add-label "$L"; APPLIED_LABELS="$APPLIED_LABELS $L" ;;
      external) L="assets:external"; gh issue edit "$ISSUE" --repo "$REPO" --add-label "$L"; APPLIED_LABELS="$APPLIED_LABELS $L" ;;
    esac
  done < <(jq -r '.assets[]?' "$WORK/classify_clean.json"; [ -n "$HAS_EXTERNAL_DEPS" ] && echo external || true)

  ITEM_ID=$(gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "https://github.com/$REPO/issues/$ISSUE" --format json -q '.id')
  gh project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
    --field-id "$STATUS_FIELD_ID" --single-select-option-id "$FINAL" >/dev/null
  if [ -n "$CATEGORY" ]; then
    gh project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
      --field-id "$CATEGORY_FIELD_ID" --single-select-option-id "$CATEGORY" >/dev/null
  fi
  gh project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
    --field-id "$PACK_HASH_FIELD_ID" --text "$PACK_SHA256" >/dev/null
  gh project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
    --field-id "$PACK_MD5_FIELD_ID" --text "$PACK_MD5" >/dev/null
  # Submission metadata fields (Game/Console/Pack URL), mirroring the CI's
  # "Record submission metadata" step so the board's columns are readable.
  gh project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
    --field-id "$GAME_FIELD_ID" --text "$GAME" >/dev/null
  gh project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
    --field-id "$PACK_URL_FIELD_ID" --text "$PACK_URL" >/dev/null
  case "$CONSOLE" in
    NES) CO="$CONSOLE_NES" ;;
    GB) CO="$CONSOLE_GB" ;;
    GBC) CO="$CONSOLE_GBC" ;;
    SMS) CO="$CONSOLE_SMS" ;;
    Other) CO="$CONSOLE_OTHER" ;;
    *) CO="" ;;
  esac
  if [ -n "$CO" ]; then
    gh project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
      --field-id "$CONSOLE_FIELD_ID" --single-select-option-id "$CO" >/dev/null
  fi
  # Seed the 👍 reaction docs/community-packs.md ranks on ("Most popular"):
  # the catalog's 👍 cell links to the submission issue, so the count starts
  # at one reaction instead of zero. The reactions API is idempotent (an
  # already-present reaction returns 200), so re-runs never double-count.
  gh api -X POST "repos/$REPO/issues/$ISSUE/reactions" -f content='+1' --silent
  echo ":: issue #$ISSUE updated (comment, labels [$APPLIED_LABELS], Project Status/Category/Hash, 👍)"

  # ---- 12. upsert mep-meta comment ----
  RECIPE_PATH="$WORK/mep_recipe.json"
  RECIPE_HASH=""
  if [ "$RECIPE_STATUS" = "present" ] && [ -f "$RECIPE_PATH" ]; then
    RECIPE_HASH=$(sha256sum "$RECIPE_PATH" | awk '{print $1}')
  fi
  PAYLOAD_PATH="$WORK/mep_meta_payload.json"
  VALIDATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  AUTHOR=$(jq -r '.author // "" | gsub("\\s+"; " ")' "$WORK/classify_clean.json")
  export RECIPE_PATH RECIPE_HASH PAYLOAD_PATH VALIDATED_AT PACK_SHA256 VERDICT APPLIED_LABELS KIND AUTHOR RECIPE_STATUS RECIPE_OK
  export GAME CONTENT_ID PACK_URL ISSUE SIBLINGS_CSV
  python3 - <<'PYEOF'
import json
import os
import sys
sys.path.insert(0, 'scripts')
from mep_recipe_common import choose_fence
from pack_id_rules import resolve_pack_id

meta = {
    "source_sha256": os.environ["PACK_SHA256"],
    "verdict": os.environ["VERDICT"],
    "labels": os.environ["APPLIED_LABELS"].split(),
    "validated_at": os.environ["VALIDATED_AT"],
}
game = os.environ.get("GAME", "").strip()
if game:
    meta["game"] = game
content_id = os.environ.get("CONTENT_ID", "").strip()
if content_id:
    meta["content_id"] = content_id
kind = os.environ.get("KIND", "")
if kind:
    meta["kind"] = kind
author = os.environ.get("AUTHOR", "").strip()
if author:
    meta["author"] = author
recipe_status = os.environ["RECIPE_STATUS"]
if recipe_status == "present" and os.path.isfile(os.environ["RECIPE_PATH"]):
    with open(os.environ["RECIPE_PATH"], encoding="utf-8") as handle:
        recipe = json.load(handle)
    deps = recipe.get("sources", {}).get("deps") or []
    meta["deps"] = [
        {"id": dep.get("id"), "sha256": dep.get("sha256"), "size": dep.get("size")}
        for dep in deps
    ]
    meta["recipe_hash"] = os.environ["RECIPE_HASH"]
    meta["recipe"] = recipe
    meta["recipe_ok"] = os.environ.get("RECIPE_OK") == "true"

# ADR-0143 identity: pack_id = origin x game (recorded so the catalog and the
# runtime resolve the same id; a declared recipe pack.id wins when present).
pack_id, _ = resolve_pack_id(os.environ["PACK_URL"], meta, int(os.environ["ISSUE"]), game=game or None)
if pack_id:
    meta["pack_id"] = pack_id

siblings = [s for s in os.environ.get("SIBLINGS_CSV", "").split(",") if s.strip().isdigit()]
if siblings:
    meta["siblings"] = [int(s) for s in siblings]

meta_json = json.dumps(meta, indent=2, sort_keys=True)
fence = choose_fence(meta_json)
body_lines = [
    "<!-- mep-meta -->",
    fence + "json",
    meta_json,
    fence,
    "",
    "dep digests: submitter-declared, verified on install",
]
payload = {"body": "\n".join(body_lines)}
with open(os.environ["PAYLOAD_PATH"], "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
PYEOF
  COMMENT_ID=$(gh api "repos/$REPO/issues/$ISSUE/comments" --paginate \
    --jq ".[] | select((.user.login == \"$OWNER\") and (.body | test(\"<!-- mep-meta -->\"))) | .id" \
    | head -n1)
  if [ -n "$COMMENT_ID" ]; then
    gh api --method PATCH "repos/$REPO/issues/comments/$COMMENT_ID" --input "$PAYLOAD_PATH" >/dev/null
    echo ":: mep-meta comment updated (id $COMMENT_ID)"
  else
    gh api --method POST "repos/$REPO/issues/$ISSUE/comments" --input "$PAYLOAD_PATH" >/dev/null
    echo ":: mep-meta comment posted"
  fi
}

# ---- 13. orchestrator: run the pipeline once per game ----
build_siblings_csv() {
  local self="$1"; shift
  local out="" n
  for n in "$@"; do
    [ "$n" = "$self" ] && continue
    out="${out:+$out,}$n"
  done
  echo "$out"
}

if [ "$SPLIT" -eq 1 ]; then
  GAME_ISSUES=()
  GAME_ISSUES[0]="$ISSUE"
  for ((i=0; i<${#SIB_ISSUES[@]}; i++)); do
    GAME_ISSUES[$((i+1))]="${SIB_ISSUES[$i]}"
  done
  # --parallel: each game validates in its own subshell (its own work dir and
  # issue, so no shared mutable state); `wait` collects every exit. Each game's
  # mep-meta/board/comment writes go to its own issue — the only shared writer
  # is ensure_community_pack_labels.sh, which is race-safe by design (--force).
  RUN_PIDS=()
  for ((i=0; i<GAME_COUNT; i++)); do
    GI="${GAME_ISSUES[$i]}"
    GW=""
    if [ "$NO_WRITE" -eq 1 ]; then
      GW="$WORK_BASE-g$i"
      SIB_CSV=""
    elif [ "$i" -eq 0 ]; then
      GW="$WORK_BASE"
      SIB_CSV=$(build_siblings_csv "$ISSUE" "${GAME_ISSUES[@]}")
    else
      GW=".cache/validate-local/$GI"
      SIB_CSV=$(build_siblings_csv "$GI" "${GAME_ISSUES[@]}")
    fi
    mkdir -p "$GW"
    echo "== validating game[$i] on issue #$GI (root '${GAME_ROOTS[$i]}') =="
    if [ "$PARALLEL" -eq 1 ]; then
      run_game "$GI" "${GAME_NAMES[$i]}" "${GAME_ROOTS[$i]}" "$SIB_CSV" "$GW" &
      RUN_PIDS+=($!)
    else
      run_game "$GI" "${GAME_NAMES[$i]}" "${GAME_ROOTS[$i]}" "$SIB_CSV" "$GW"
    fi
  done
  if [ "$PARALLEL" -eq 1 ]; then
    FAILED=0
    for p in "${RUN_PIDS[@]}"; do
      wait "$p" || FAILED=1
    done
    if [ "$FAILED" -eq 1 ]; then
      echo "error: at least one parallel per-game validation failed" >&2
      exit 1
    fi
  fi
  # Linking comments (ADR-0143): the primary lists the siblings; each sibling
  # links back to the full split set.
  if [ "$NO_WRITE" -eq 0 ] && [ "$PREPARE_ONLY" -eq 0 ] && [ "${#SIB_ISSUES[@]}" -gt 0 ]; then
    LINKS=""
    for n in "${SIB_ISSUES[@]}"; do
      LINKS="$LINKS [#$n](https://github.com/$REPO/issues/$n)"
    done
    gh issue comment "$ISSUE" --repo "$REPO" --body "This submission contains $GAME_COUNT game packs, so the pipeline split it into one issue per game — each pack keeps its own identity and catalog slot (ADR-0143). This issue covers **${GAME_NAMES[0]}**; the sibling issues are:$LINKS"
    for ((i=0; i<${#SIB_ISSUES[@]}; i++)); do
      SN="${SIB_ISSUES[$i]}"
      gh issue comment "$SN" --repo "$REPO" --body "Automated sibling of #$ISSUE — part of a split submission (ADR-0143). This issue covers **${GAME_NAMES[$((i+1))]}**; the sibling issues are: [#$ISSUE](https://github.com/$REPO/issues/$ISSUE)$LINKS"
    done
  fi
else
  run_game "$ISSUE" "$GAME" "" "" "$WORK_BASE"
fi

echo "== done — work in $WORK_BASE"
