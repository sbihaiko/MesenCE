#!/usr/bin/env bash
# Verifies .github/AGENTS.md (F6.2a, AC-4): records the ADR-0138 §13 recipe
# handoff as a Local Contracts bullet — the CI-runtime path
# `$RUNNER_TEMP/mep_recipe.json` (explicitly runner-local, never a path
# inside the checkout) and the three-valued `recipe_status` step output
# (absent/present/refused). This slice only *documents* the contract; the
# assembly step itself is F6.2b and is not implemented here, so this check
# reads .github/AGENTS.md only — it never touches any workflow file.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOC="$REPO_ROOT/.github/AGENTS.md"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$DOC" ] || fail "file not found: $DOC"

grep -qF 'ADR-0138' "$DOC" || fail "$DOC does not cite ADR-0138"
grep -qF '§13' "$DOC" || fail "$DOC does not cite ADR-0138 §13"

# The runner-local handoff path, documented exactly, plus prose stating it
# is runner-local and must not live inside the repo/checkout.
grep -qF '$RUNNER_TEMP/mep_recipe.json' "$DOC" \
  || fail "$DOC does not document the \$RUNNER_TEMP/mep_recipe.json handoff path"
grep -qi 'runner-local' "$DOC" \
  || fail "$DOC does not state that the recipe handoff path is runner-local"
grep -qi 'checkout' "$DOC" \
  || fail "$DOC does not state that the recipe file must never live inside the checkout"

# The three-valued recipe_status output, all three values present.
grep -qF 'recipe_status' "$DOC" \
  || fail "$DOC does not document the recipe_status step output"
for value in '`absent`' '`present`' '`refused`'; do
  grep -qF "$value" "$DOC" \
    || fail "$DOC does not document the recipe_status value $value"
done

echo "PASS: .github/AGENTS.md documents the ADR-0138 §13 recipe handoff (\$RUNNER_TEMP/mep_recipe.json, runner-local, never in the checkout) and the three-valued recipe_status output (absent/present/refused)"
