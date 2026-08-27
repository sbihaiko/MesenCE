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
  `ubuntu-latest` job that runs `dotnet test UI.Tests/UI.Tests.csproj` and
  then `make core-unit-tests` (the framework-free C++ harness in
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
  HD/MEP pack submissions (not a free-text issue): pack link, target
  game/ROM + region, console dropdown, author/credits, a required
  rights-confirmation checkbox, and an optional description. Sets
  `labels: [community-pack]`
  and links `docs/hd-pack-authoring.md`. Structurally checked by
  `scripts/checks/verify_community_pack_issue_template.py`.
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
  instructions, in the prompt. Dispatches
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
- `grep -E "make core-unit-tests" .github/workflows/unit-tests.yml`
- `grep -cE "InteropDLL|SDL2" .github/workflows/unit-tests.yml` (expected: 1,
  the explanatory comment line only — 0 actual build/link steps)
- `grep -E "dotnet-version: 10" .github/workflows/unit-tests.yml
  .github/workflows/build.yml .github/workflows/dotnet-format-check.yml`
- `grep -E "ADR-0131" .github/AGENTS.md` (this file's own invariant
  section cites the ADR; the workflow file does not need to)
- `grep -E "exclude-regex" .github/workflows/clang-format-check.yml`
- `python3 scripts/checks/verify_community_pack_issue_template.py`

## Child DOX Index

(none — leaf directory; `actions/` holds reusable composite actions with no
independent contract of their own)
