#!/usr/bin/env bash
# Local equivalent of community-pack-validate.yml's classify pipeline
# (F6.5). Fetches a community pack from its issue, lints it, runs the
# classify prompt from .github/ai/validate-classify.md through Claude, then
# deterministically assembles/validates the MEP recipe (when external assets
# are declared) and records state on the issue — comment, labels, Project
# Status/Category/Pack Hash, and the `<!-- mep-meta -->` comment.
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
#   --work <dir>           Work directory override (default: .cache/validate-local/<issue>).
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
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *) ISSUE="$1" ;;
  esac
  shift
done

if [ -z "$ISSUE" ]; then
  echo "error: issue number required" >&2
  sed -n '2,30p' "$0" >&2
  exit 1
fi
case "$LLM" in claude|session) ;; *) echo "error: --llm must be claude or session" >&2; exit 1 ;; esac

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# In supervised-prepare mode (--llm session with no classify output yet) the
# run is a dry prep: a lint failure must be REPORTED, not written to the
# issue/board — the apply path only runs once the classify step is real.
if [ "$LLM" = "session" ] && [ ! -f "$WORK/classify_raw.json" ]; then
  PREPARE_ONLY=1
fi
# macOS Python.org builds don't ship a default CA bundle, so urllib (used by
# fetch_pack.py) fails TLS verification locally. Point at certifi when present;
# CI runners ship system certs and are unaffected.
if python3 -c "import certifi" 2>/dev/null; then
  export SSL_CERT_FILE="$(python3 -c 'import certifi; print(certifi.where())')"
fi
WORK="${WORK:-.cache/validate-local/$ISSUE}"
mkdir -p "$WORK"
echo "work=$WORK"

# ---- 1. read the issue ----
BODY=$(gh issue view "$ISSUE" --repo "$REPO" --json body -q '.body')
printf '%s' "$BODY" > "$WORK/issue_body.txt"

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
python3 scripts/fetch_pack.py "$PACK_URL" "$WORK/pack_download.bin" \
  --max-bytes "$MAX_PACK_BYTES" --allowlist scripts/pack_host_allowlist.json
PACK_SHA256=$(sha256sum "$WORK/pack_download.bin" | awk '{print $1}')
PACK_MD5=$(md5sum "$WORK/pack_download.bin" | awk '{print $1}')
echo "sha256=$PACK_SHA256"
echo "md5=$PACK_MD5"

# ---- 3. lint ----
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
  exit 0
fi

# ---- 4. render the classify prompt from the .md ----
EXT="$(printf '%s' "$BODY" | sed -n '/^### *External assets/I,$p' | sed '1d' | sed '/^### /,$d' | sed '/^[[:space:]]*$/d' || true)"
if [ -n "$EXT" ]; then
  SUFFIX="THE SUBMISSION DECLARES EXTERNAL ASSETS (MEP-recipe-v1 §3.3, user_supplied deps hosted separately) — this is the ADR-0138 §2/§7 EXCEPTION: the referenced section counts as usable, verdict MUST be \"accepted\", and the recipe object MUST be filled (deps user_supplied, no sha256/size). Do not apply MEP-v1 §5's missing-file rule to these:
  $(printf '%s' "$EXT" | sed 's/^/  - /')"
else
  SUFFIX=""
fi

python3 - "$PROMPT_FILE" "$ISSUE" "$SUFFIX" "$WORK" <<'PY'
import os
import re
import sys

path, issue, suffix, work = sys.argv[1:5]
text = open(path, encoding="utf-8").read()
# rsplit: the markers also appear in prose (the "<!-- SCHEMA -->" mention in
# the doc header), so split on the LAST occurrence — the real delimiters.
prompt = text.rsplit("<!-- PROMPT -->", 1)[1].rsplit("<!-- SCHEMA -->", 1)[0].strip()
schema = text.rsplit("<!-- SCHEMA -->", 1)[1].strip()
prompt = prompt.replace("{{ISSUE_NUMBER}}", issue).replace("{{EXTERNAL_ASSETS_SUFFIX}}", suffix)
with open(os.path.join(work, "classify_prompt.md"), "w", encoding="utf-8") as f:
    f.write(prompt + "\n")
with open(os.path.join(work, "classify_schema.json"), "w", encoding="utf-8") as f:
    f.write(schema + "\n")
PY
echo "prompt rendered -> $WORK/classify_prompt.md"

# ---- 5. run classify ----
SCHEMA=$(cat "$WORK/classify_schema.json")
if [ "$LLM" = "claude" ]; then
  MODEL="${MODEL:-claude-sonnet-4-5}"
  echo ":: running claude headless (--llm claude, model $MODEL)..."
  # Run with cwd=$WORK so the prompt's relative paths (pack_download.bin,
  # mep_lint_output.txt) resolve to this issue's isolated work dir — safe for
  # parallel invocations; docs/ is symlinked so the spec references resolve.
  # The prompt goes via stdin (an argv prompt + multi-MB lint output would hit
  # "Argument list too long"). --output-format text keeps classify_raw.json to
  # just the model's JSON (the default json emits the whole JSONL transcript,
  # ~3MB). --mcp-config {} drops the MCP servers from the system prompt, which
  # otherwise inflate every call to ~119k input tokens.
  ( cd "$WORK" && ln -sfn "$ROOT/docs" docs && claude -p \
    --output-format text --json-schema "$SCHEMA" \
    --mcp-config '{"mcpServers":{}}' --allowedTools "Read,Glob,Grep" \
    --model "$MODEL" < classify_prompt.md > classify_raw.json )
elif [ -f "$WORK/classify_raw.json" ]; then
  echo ":: using existing $WORK/classify_raw.json"
else
  echo ":: --llm session — classify prompt rendered to:"
  echo "   $WORK/classify_prompt.md"
  echo "   Read it (plus $WORK/mep_lint_output.txt and $WORK/pack_download.bin),"
  echo "   produce the JSON per the schema in $WORK/classify_schema.json,"
  echo "   save it to $WORK/classify_raw.json, then re-run this script."
  exit 0
fi

# ---- 6. sanitize classify JSON (repair real newlines inside strings) ----
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

# ---- 7. assemble + gate the MEP recipe (deterministic) ----
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

# ---- 8. apply verdict (deterministic writer) ----
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

echo "== apply (verdict=$VERDICT, label=$LABEL, kind=$KIND, downgraded=$DOWNGRADED) =="
if [ "$NO_WRITE" -eq 1 ]; then
  echo ":: --no-write — not posting comment/labels/board/mep-meta. Draft comment:"
  cat "$WORK/verdict_comment.txt"
else
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
  # Seed the 👍 reaction docs/community-packs.md ranks on ("Most popular"):
  # the catalog's 👍 cell links to the submission issue, so the count starts
  # at one reaction instead of zero. The reactions API is idempotent (an
  # already-present reaction returns 200), so re-runs never double-count.
  gh api -X POST "repos/$REPO/issues/$ISSUE/reactions" -f content='+1' --silent
  echo ":: issue #$ISSUE updated (comment, labels [$APPLIED_LABELS], Project Status/Category/Hash, 👍)"
fi

# ---- 9. upsert mep-meta comment ----
if [ "$NO_WRITE" -eq 0 ]; then
  RECIPE_PATH="$WORK/mep_recipe.json"
  RECIPE_HASH=""
  if [ "$RECIPE_STATUS" = "present" ] && [ -f "$RECIPE_PATH" ]; then
    RECIPE_HASH=$(sha256sum "$RECIPE_PATH" | awk '{print $1}')
  fi
  PAYLOAD_PATH="$WORK/mep_meta_payload.json"
  VALIDATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  AUTHOR=$(jq -r '.author // "" | gsub("\\s+"; " ")' "$WORK/classify_clean.json")
  export RECIPE_PATH RECIPE_HASH PAYLOAD_PATH VALIDATED_AT PACK_SHA256 VERDICT APPLIED_LABELS KIND AUTHOR RECIPE_STATUS RECIPE_OK
  python3 - <<'PYEOF'
import json
import os
import sys
sys.path.insert(0, 'scripts')
from mep_recipe_common import choose_fence

meta = {
    "source_sha256": os.environ["PACK_SHA256"],
    "verdict": os.environ["VERDICT"],
    "labels": os.environ["APPLIED_LABELS"].split(),
    "validated_at": os.environ["VALIDATED_AT"],
}
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
fi

echo "== done — work in $WORK"
