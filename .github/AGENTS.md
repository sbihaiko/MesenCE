# .github/

## Purpose

GitHub Actions CI/CD: build, format-check, and test workflows for the
project.

## Ownership

Owned at the repo-infra level. Workflow files are the source of truth for
what CI actually runs; this doc records why they're split the way they are.

## Local Contracts

- `workflows/build.yml` — full native + UI release build.
- `workflows/clang-format-check.yml` — C++ formatting gate (`clang-format` 20,
  `check-path: ./`). Runs on push to `main` (the product branch) and on
  every PR. Excludes vendored `Utilities/Audio/tsf.h` (TinySoundFont);
  that header is also wrapped in `clang-format off/on`.
  `master` is a frozen full-console snapshot and is not gated here.
- `workflows/dotnet-format-check.yml` — `dotnet format --verify-no-changes`
  against `Mesen.sln` (Windows). Only touches projects that are members of
  the `.sln`.
- `workflows/tests.yml` — Windows-only ROM regression suite (PGOHelper +
  the private `MesenTests` repo). Requires a full native + UI build. Not
  touched by the unit-tests workflow below.
- `workflows/unit-tests.yml` — Fase 0 of the now-completed unit-test plan
  (see git history for `docs/roadmap/plano-testes-unitarios.md`):
  `ubuntu-latest` job that runs
  `./scripts/verify-ui-logic-firewall.sh` (ADR-0123, H5 — the fast
  pre-check; the dual-compile is the authoritative gate), then
  `dotnet test UI.Tests/UI.Tests.csproj` and then `make core-unit-tests`
  (the framework-free C++ harness in
  `scripts/core_unit_tests.cpp`). Deliberately independent of `tests.yml`:
  no native build, no SDL2, no `MesenCore`, so it stays fast and runs on
  every push/PR regardless of the Windows ROM suite's state. `UI.Tests.csproj`
  is intentionally NOT a member of `Mesen.sln`, so this workflow does not go
  through `dotnet-format-check.yml` or `build.yml`'s restore/publish flow
  either. This file's Work Guidance section (ADR-0131) is the normative
  contract for the job's invariants and toolchain/version policy — the
  workflow file itself carries no restatement of them, so read them here,
  not there, and keep this doc in sync when either side changes.
- `ISSUE_TEMPLATE/community-pack.yml` — GitHub Issue Form for community
  HD/MEP pack submissions (not a free-text issue). Deliberately minimal:
  pack link, target game/ROM + region and a console dropdown, all
  required, and nothing else. An intro promising three fields plus a bot
  comment with the result, one-line field descriptions, and a closing
  `docs/hd-pack-authoring.md` link explicitly marked as not required
  reading. Sets `labels: [community-pack]`.
  Removed on purpose (`verify_community_pack_issue_template.py` fails if
  any comes back): `author_credits` — the classify step discovers
  authorship from the pack's own manifest/README and records it as
  mep-meta's `author`, which is what the catalog's Author column reads;
  `description`; and the ADR-0138 §12 split-distribution pair
  `external_assets`/`external_assets_license`. The recipe parser still
  accepts an "External assets" section typed into an issue body by hand
  (`<url> [<sha256>] [<size>]` per non-empty line, `#`-comments and blank
  lines ignored, a line missing `sha256` disabling recipe assembly), so
  the pipeline behind it is unchanged — a submission simply no longer
  asks for it, and its `license` therefore defaults to "unknown".
  There is no distribution-rights checkbox either (dropped in
  `b62f0bbc`). Structurally checked by
  `scripts/checks/verify_community_pack_issue_template.py`.
- `workflows/community-pack-submitted.yml` — trigger-only wrapper that
  extracts the pack URL and mode, then calls the reusable validate
  workflow. Concurrency group is per issue number. `cancel-in-progress`
  is `${{ github.event_name == 'issues' }}` (F6.0, ADR-0138): a newer
  opened/edited submission supersedes a stale run, but an `issue_comment`
  (including the verdict comment this pipeline posts) must not cancel the
  in-flight run, or the catalog-dispatch step is lost. `/revalidate`
  comments queue behind an in-flight run instead of killing it. Checked
  by `scripts/checks/verify_community_pack_submitted_workflow.py`.
- `workflows/community-pack-validate.yml` — reusable (`workflow_call` only,
  no trigger of its own) validate/classify pipeline for the "Community
  HD/MEP Packs" triage board (GitHub Project "MesenCE Community Packs",
  project number 3, owner `sbihaiko`). Referenced by value only, never
  created/rediscovered: Project node id, the Status field's five option
  ids, and the Pack Hash field id. Enforces a host allow-list
  (`github.com/*/releases/*`, `raw.githubusercontent.com`,
  `gist.githubusercontent.com`, `gist.github.com`) and a 300MB cap before
  and during the download, always records the pack's `sha256` to Pack
  Hash, calls `scripts/mep_lint.py` unmodified, and — only on lint
  success — classifies the pack via `anthropics/claude-code-action`
  restricted to comment/label/Project-move tools (no `Bash`), with the
  pack's own file names/`pack.json`/issue text framed as data, never
  instructions, in the prompt. The classify step carries
  `timeout-minutes: 15` (F6.0) so a hung Claude Code Action cannot hold
  the runner for the job's 6-hour default. Dispatches
  `workflows/community-pack-catalog.yml` by name (never opens it) when the
  final Status is one of the two "Aceito" states. Requires the caller to
  supply a `PROJECT_PAT` PAT (`repo` + `project` + `read:org` scopes —
  `read:org` is required by `gh project` commands to resolve a
  personal-account owner, confirmed via a live "unknown owner type"
  failure without it) and either
  `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` as repo secrets — this
  workflow only documents those names, never creates them. See
  `scripts/checks/verify_community_pack_validate_workflow.py` for its
  structural contract.
- **Recipe handoff (ADR-0138 §13, amends §9; F6.2b complete).**
  The "Classify pack" step's `--json-schema` now carries an OPTIONAL
  nested `recipe` property (`ops`/`deps`/`pack`, per
  `docs/specs/MEP-recipe-v1.md`) with its own `"required":["ops","deps","pack"]`
  — separate from, and never added to, the unchanged top-level
  `"required":["verdict","assets","comment"]` — because classify (the LLM)
  never computes a hash: no `sources` block or hash-bearing field exists
  anywhere in this schema (ADR-0138 §4). The prompt states this
  explicitly. Checked by `verify_community_pack_validate_workflow.py`'s
  `check_classify_recipe_fragment_required`,
  `check_classify_top_level_required_unchanged`, and
  `check_classify_schema_no_sources_field`.
  `community-pack-validate.yml`'s "Assemble MEP recipe" step (`id:
  assemble-recipe`, runs right after "Classify pack") writes the MEP
  Recipe to `$RUNNER_TEMP/mep_recipe.json` — a GitHub Actions runner-local
  temp path, never a path inside the checkout, so the recipe can never be
  mistaken for, or committed as, a repo artefact. Nothing under this repo
  (this workflow, `scripts/`, or anywhere else) may write `mep_recipe.json`
  into the checkout; the file exists only on the runner's local disk for
  the duration of the job. It fetches the issue body itself via `gh issue
  view "$ISSUE_NUMBER" --repo "$REPO" --json body -q .body` — never the
  triggering event's payload (§17), since this reusable `workflow_call`
  workflow's callers include non-`issues` triggers (drift-check's
  `workflow_dispatch`/schedule) — and calls `scripts/mep_recipe.py
  assemble-sources` with classify's optional `recipe` fragment, the issue
  body, and the CI-computed primary sha256 (`steps.hash.outputs.sha256`).
  The step exposes one step output, `recipe_status`, with exactly three
  values: `absent` (the submission declared no `external_assets`, or
  classify emitted no recipe fragment at all), `present` (a recipe was
  assembled and written to the path above), and `refused` (assets were
  declared but at least one dependency line lacks a `sha256`, so assembly
  was declined per §3/§12). Every downstream reader — the gate step, the
  `assets:external` label branch, `apply-verdict`'s downgrade expression,
  and the mep-meta `recipe_hash` comment — branches on this enum instead
  of re-deriving "is there a recipe?". Checked by
  `verify_community_pack_validate_workflow.py`'s
  `check_assemble_recipe_step_present`,
  `check_assemble_recipe_issue_body_via_gh`,
  `check_assemble_recipe_runner_temp_handoff`,
  `check_recipe_status_three_values`, and `check_no_github_event_issue`,
  and by `scripts/checks/verify_agents_md_recipe_handoff.sh` for this
  prose.
  A "Recipe gate (mep_recipe.py validate + dry-run, deps stubbed by name)"
  step (`id: recipe-gate`, runs right after "Assemble MEP recipe" and
  before "Apply classification verdict") is gated on
  `steps.assemble-recipe.outputs.recipe_status == 'present'` — **never**
  `!= 'absent'`, which would also wrongly fire for `refused` (§2/§13: a
  refused submission's pre-ADR verdict path must stay completely
  untouched). It runs `python3 scripts/mep_recipe.py validate` against
  the handoff path above, then (only if that passed) `python3
  scripts/mep_recipe.py dry-run` against the already-downloaded primary
  (`pack_download.bin`) — with no `--dep PATH` ever passed, since CI
  never fetches or hashes external dependency content (§16). Every
  declared dependency is therefore "stubbed by [its] declared name"
  simply by never being supplied: `mep_recipe.py`'s existing missing-dep
  handling treats every dep id from `sources.deps` as missing, skips its
  ops, and withholds its patch/section from `pack.json`, exactly as the
  default `apply_patch_only_if_complete` policy already does for a
  `user_supplied` dep — no dedicated CI-only flag is needed. `RECIPE_OK`
  is set to `false` (never a hard workflow failure) whenever either call
  exits non-zero, which also covers the rarer case of a `user_supplied:
  false` dep or an explicit `apply_patch_only_if_complete: false` policy
  demanding content CI cannot supply; the gate simply reports
  `recipe_ok=false` and leaves the outcome to `apply-verdict`'s
  downgrade-only expression (§10). The step exposes exactly
  one boolean output, `recipe_ok`, and never adds a
  label, posts a comment, or moves the Project Status field itself —
  `apply-verdict` remains the sole verdict writer (§10). Checked by
  `verify_community_pack_validate_workflow.py`'s
  `check_recipe_gate_step_present_and_gated` and
  `check_recipe_gate_never_uses_inverted_condition`.
  `apply-verdict` (`id: apply-verdict`, "Apply classification verdict")
  stays the SOLE verdict/label writer (§10): it reads
  `steps.assemble-recipe.outputs.recipe_status` and
  `steps.recipe-gate.outputs.recipe_ok` and downgrades `accepted` to
  `invalid` with one literal bash condition inside its `run:` block —
  `[ "$RECIPE_STATUS" = "present" ] && [ "$RECIPE_OK" != "true" ]` —
  deliberately not a step-level `if:`, since that would decide whether the
  whole verdict/label step runs at all rather than downgrading its
  outcome. The same step's existing asset-label case loop gains an
  `external` arm applying `assets:external`, fed in only when
  `recipe_status == 'present'` and the assembled recipe's
  `sources.deps` array (read back from `$RUNNER_TEMP/mep_recipe.json`) is
  non-empty (§6) — never derived from classify's own `assets` enum, which
  has no "external" member. `apply-verdict` exposes three step outputs:
  `verdict` (the effective, post-downgrade verdict), `labels` (every label
  actually applied to the issue), and, since F6.3b (ADR-0138 §29), `kind`
  — set by a second `case` on the already-decided `$CATEGORY`
  (`"$CATEGORY_FULL_MEP") KIND="mep"`, `"$CATEGORY_PARTIAL_HD")
  KIND="hd-legacy"`, mirroring rather than re-deriving the CATEGORY
  selection, since today's binary accepted/invalid verdict can't tell
  "mep" from "hd-legacy" by itself) so the mep-meta upsert step below can
  consume all three without recomputing. The two `KIND=` literals are
  textually consistent with `scripts/mei_rules.STATUS_TO_KIND`'s own
  values (checked by reading `mei_rules.py`'s source directly, never by
  importing it). Checked by `verify_community_pack_validate_workflow.py`'s
  `check_apply_verdict_downgrade_expression`,
  `check_apply_verdict_external_label_branch`,
  `check_apply_verdict_exposes_outputs`, and
  `check_apply_verdict_kind_matches_mei_rules_status_to_kind`.
  **"Upsert mep-meta comment" (`id: upsert-mep-meta`, F6.2b complete;
  fence fix + `kind` field F6.3b).** Runs right after `apply-verdict`, on
  EVERY successful classify pass (`if: steps.classify.outcome ==
  'success'`) — deliberately never gated on `recipe_status == 'present'`
  (§5/§13/§18): a submission with no assembled recipe (`absent`/
  `refused`) still gets its verdict, labels and `source_sha256` recorded,
  just without the `deps`/`recipe_hash` fields (omitted entirely, never
  emitted empty/null). `verdict` and `labels` are read verbatim from
  `apply-verdict`'s own outputs — never recomputed; `kind` (F6.3b, §29) is
  read the same way and, when non-empty, copied into the payload's own
  `kind` field (also omitted, never emitted empty, when apply-verdict
  picked no CATEGORY). The `<!-- mep-meta -->`-marked comment is bot-owned
  and rewritten WHOLESALE on every pass (§5): the step finds it via `gh
  api` (`GET /repos/$REPO/issues/$ISSUE_NUMBER/comments`, `--jq` matching
  the marker), then `gh api --method PATCH` its body outright — never a
  read-modify-merge with whatever it said before — or `gh api --method
  POST` a new comment when none exists yet. The comment body (embedded
  JSON metadata block plus the literal provenance line, "dep digests:
  submitter-declared, verified on install", §16) and the API request
  payload are both built with Python's `json` module (a `python3 -
  <<'PYEOF'` heredoc reading the step's own env vars), never bash string
  concatenation. Since F6.3b (ADR-0138 §33), the JSON block's opening/
  closing fence is no longer a hardcoded literal `` ```json ``/`` ``` ``
  pair — `json.dumps` does not escape backticks, so a submitter's
  `hints`/`license` value containing a run of 3+ backticks used to
  truncate the block early. The heredoc now does `sys.path.insert(0,
  'scripts')` (the same pattern the "Enforce host allow-list" step above
  already uses) and calls `mep_recipe_common.choose_fence(meta_json)` to
  pick a fence strictly longer than any backtick run already in the
  serialized payload, matching the reader-side rule `mep_recipe.py`'s
  `FENCE`/`load_recipe` use (see `mep_recipe_common.py` below;
  `mep_meta_parser.py`'s own `JSON_FENCE_RE` reader is a known, tracked
  gap — still bare-3-backticks, out of F6.3b's file list, not silently
  patched here). `recipe_hash` is `sha256sum` of
  `$RUNNER_TEMP/mep_recipe.json` itself — a hash of the recipe DOCUMENT,
  never of dep contents; dep `sha256`/`size` are copied straight from the
  assembled recipe's `sources.deps` (submitter-declared, never
  CI-verified, §11/§16). Checked by
  `verify_community_pack_validate_workflow.py`'s
  `check_mep_meta_step_present_and_not_gated_on_recipe_status`,
  `check_mep_meta_find_then_patch`, `check_mep_meta_marker_in_comment_body`,
  `check_mep_meta_provenance_line`, `check_mep_meta_body_built_via_python_json`,
  `check_mep_meta_omits_deps_and_recipe_hash_when_absent`, and
  `check_mep_meta_fence_not_hardcoded`. F6.2b is complete end-to-end
  (classify schema → assembly → gate → apply-verdict → mep-meta upsert);
  F6.3b hardens the `kind` field and the fence on top of it.

## Work Guidance

- `unit-tests.yml` must never link `InteropDLL`/`MesenCore`, never require
  SDL2, and never require a platform SDK or ROM corpus. A self-contained
  compile of explicitly listed `Core/`/`Utilities/` sources (as
  `make core-unit-tests` does) is in scope; anything that needs the `core`
  makefile target belongs in `build.yml`/`tests.yml`.
- The `ui-tests` job id now covers both the C# and the C++ host-free
  suites (steps `Run unit tests` and `Run core unit tests`), so a later
  rename (e.g. to something like `host-free-tests`) is a known, deliberate
  option, not a surprise — see ADR-0131 for why it isn't done now.
- `make core-unit-tests` in this workflow is intentionally clang-only
  (makefile default `CXX := clang++`) for cheapness; gcc and arm64
  coverage of the `Core/` sources it compiles is `build.yml`'s job via
  `CORESRC`. Only `scripts/core_unit_tests.cpp` itself is clang-gated.
- `actions/setup-dotnet`'s `dotnet-version` pins `10.x` in
  `unit-tests.yml`, matching `build.yml`'s `10.x`; `dotnet-format-check.yml`
  pins `10.0.x` for its own, separate Windows-only `dotnet format` check.
  These are two independent pins, not one tracking the other — keep
  `unit-tests.yml` aligned with `build.yml`'s `10.x`, not with
  `dotnet-format-check.yml` (ADR-0131 item 4, option A: the doc matches the
  files as they are).

## Verification

- `grep -E "dotnet test" .github/workflows/unit-tests.yml`
- `grep -E "verify-ui-logic-firewall" .github/workflows/unit-tests.yml`
  (the step must precede "Run unit tests")
- `grep -E "make core-unit-tests" .github/workflows/unit-tests.yml`
- `grep -cE "InteropDLL|SDL2" .github/workflows/unit-tests.yml` (expected: 1,
  the explanatory comment line only — 0 actual build/link steps)
- `grep -E "dotnet-version: 10" .github/workflows/unit-tests.yml
  .github/workflows/build.yml .github/workflows/dotnet-format-check.yml`
- `grep -E "ADR-0131" .github/AGENTS.md` (this file's own invariant
  section cites the ADR; the workflow file does not need to)
- `grep -E "exclude-regex" .github/workflows/clang-format-check.yml`
- `python3 scripts/checks/verify_community_pack_issue_template.py`
- `python3 scripts/checks/verify_community_pack_submitted_workflow.py`
- `python3 scripts/checks/verify_community_pack_validate_workflow.py`
- `grep -F "cancel-in-progress: \${{ github.event_name == 'issues' }}" .github/workflows/community-pack-submitted.yml`
- `grep -A2 "id: classify" .github/workflows/community-pack-validate.yml | grep timeout-minutes`
- `./scripts/checks/verify_agents_md_recipe_handoff.sh`

## Child DOX Index

(none — leaf directory; `actions/` holds reusable composite actions with no
independent contract of their own)
