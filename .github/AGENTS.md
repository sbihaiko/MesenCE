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
  either.

## Work Guidance

- Keep `unit-tests.yml` cheap: it must never require the native
  `InteropDLL`/`MesenCore` build or SDL2. If a future `UI.Tests` addition
  needs either, that addition belongs in `tests.yml`/`build.yml` instead,
  not here.
- `actions/setup-dotnet` version and the `dotnet-version` value should track
  `dotnet-format-check.yml`'s (currently `10.0.x`) unless there's a
  documented reason to diverge.

## Verification

- `grep -E "dotnet test" .github/workflows/unit-tests.yml`
- `grep -E "make core-unit-tests" .github/workflows/unit-tests.yml`
- `grep -E "exclude-regex" .github/workflows/clang-format-check.yml`

## Child DOX Index

(none — leaf directory; `actions/` holds reusable composite actions with no
independent contract of their own)
