# ADR-0131: unit-tests.yml contract stated as invariants; clang-only C++ step; dotnet-version parity

- Status: accepted (2026-08-27, work requested via docs/roadmap/PRD-mesence-enhancement-ecosystem.md; was: documentation edits to `.github/AGENTS.md` pending; restored 2026-09-01 from b0b334b0^ after accidental deletion; work shipped 2026-08-28 as slice H2 of docs/roadmap/PRD-mesence-enhancement-ecosystem.md (`.github/AGENTS.md` invariants + clang-only note present))
- Date: 2026-08-27
- Consolidates: ADR-0086, ADR-0087, ADR-0088, ADR-0089, ADR-0090, ADR-0091

## Context
After ADR-0126 the `ui-tests` job in `.github/workflows/unit-tests.yml` runs
both `dotnet test UI.Tests/UI.Tests.csproj` and `make core-unit-tests`. Three
contract-vs-reality drifts in `.github/AGENTS.md` Work Guidance
(lines 70–76) followed, none of them code defects:

1. Tool-name phrasing. The guardrail reads "Keep `unit-tests.yml` cheap: it
   must never require the native `InteropDLL`/`MesenCore` build or SDL2. If a
   future `UI.Tests` addition needs either, that addition belongs in
   `tests.yml`/`build.yml`". The C++ step complies with the letter (it links
   only three named `.cpp` files plus `Utilities/*.cpp`, no MesenCore/SDL2),
   but the wording no longer distinguishes "cheap self-contained compile of
   listed sources" from "full native build", and the job id `ui-tests` is
   narrower than its content (ADR-0086, ADR-0088, ADR-0091).
2. Compiler coverage. `make core-unit-tests` runs with no flags, so it uses the
   makefile's `CXX := clang++` default (`makefile:17`; `USE_GCC=true` selects
   `g++` at line 12). `build.yml`'s Linux matrix exercises both toolchains
   (`make_flags: "USE_GCC=true"`, `build.yml:83`). ADR-0087 proposed either
   documenting the step as clang-only or adding a `USE_GCC` matrix. ADR-0089
   showed the matrix premise is wrong: `makefile:142` defines
   `CORESRC := $(shell find Core -name '*.cpp')`, so
   `Core/Shared/Audio/ChannelRoleClassifier.cpp` and
   `Core/Shared/EnhancementPacks/MepPack.cpp` are already compiled by
   `build.yml` under `USE_GCC=true` on x64 and arm64; the only file gated
   solely on clang is the harness `scripts/core_unit_tests.cpp` itself, and
   the recipe passes `-w`, so only hard compile errors matter. ADR-0090
   resolved the conflict in favour of one cheap lane plus a doc line.
3. Version drift. `.github/AGENTS.md` says the `dotnet-version` value should
   track `dotnet-format-check.yml`'s "(currently `10.0.x`)"; `unit-tests.yml:34`
   pins `10.x`, `dotnet-format-check.yml:24` pins `10.0.x`, and `build.yml`
   uses `10.x` at lines 100/146/197. The version bullet has no Verification
   grep, unlike the `dotnet test` / `make core-unit-tests` claims, which is why
   it drifted unnoticed (ADR-0091).

## Decision
Rewrite the `unit-tests.yml` contract in `.github/AGENTS.md` as invariants
plus grep-able verification. Keep the single job; no rename, no matrix.

- [ ] Work Guidance, guardrail bullet: replace the tool-name sentence with the
      invariant — "`unit-tests.yml` must never link `InteropDLL`/`MesenCore`,
      never require SDL2, and never require a platform SDK or ROM corpus. A
      self-contained compile of explicitly listed `Core/`/`Utilities/` sources
      (as `make core-unit-tests` does) is in scope; anything that needs the
      `core` makefile target belongs in `build.yml`/`tests.yml`."
- [ ] Add a note that the `ui-tests` job id now covers both the C# and the C++
      host-free suites (steps `Run unit tests` and `Run core unit tests`), so a
      later rename is a known, deliberate option rather than a surprise.
- [ ] Add one line: "`make core-unit-tests` in this workflow is intentionally
      clang-only (makefile default `CXX := clang++`) for cheapness; gcc and
      arm64 coverage of the `Core/` sources it compiles is `build.yml`'s job via
      `CORESRC`. Only `scripts/core_unit_tests.cpp` itself is clang-gated."
- [ ] Fix the version bullet: either change the text to state the actual
      values (`unit-tests.yml` and `build.yml` pin `10.x`;
      `dotnet-format-check.yml` pins `10.0.x`) and which one is the reference,
      or align the workflow pins — pick one and make the doc match the files.
- [ ] Verification block: add grep lines that keep the new claims honest, e.g.
      `grep -E "dotnet-version: 10" .github/workflows/unit-tests.yml
      .github/workflows/dotnet-format-check.yml` and
      `grep -cE "InteropDLL|SDL2" .github/workflows/unit-tests.yml` (expected
      0 outside comments), alongside the existing `dotnet test` /
      `make core-unit-tests` greps.

## Consequences
- The guardrail stops going stale whenever the lane gains a step of a
  different kind; future readers have a stated rule for what may join
  `ui-tests`.
- Toolchain coverage of the harness is recorded as a deliberate choice: one
  unpinned clang on `ubuntu-latest`. A clang-only breakage in
  `scripts/core_unit_tests.cpp` would land green in `build.yml` but red here,
  which is the intended signal.
- `dotnet-version` parity becomes mechanically checkable instead of a prose
  claim.
- Job/matrix split for failure attribution stays deferred (see ADR-0126); the
  named step already attributes failures.
- All items are edits to `.github/AGENTS.md` (and possibly one workflow pin);
  no code change.

## Alternatives
- Add a `USE_GCC=true`/default matrix to the C++ step (ADR-0087's second
  branch): rejected per ADR-0089/0090 — doubles the cheap lane's cost to gate
  one test-only file whose `Core/` dependencies are already gcc-built by
  `build.yml`.
- Rename the job (e.g. `host-free-tests`) now: rejected — a rename churns
  branch-protection/status-check names for a wording problem; noted as a
  known option instead.
- Split into two jobs so C#/C++ failures show separately (ADR-0085 carried
  into ADR-0088): rejected — step names already attribute failure; see
  ADR-0126.
- Leave `.github/AGENTS.md` as-is and rely on the existing Verification greps:
  rejected — the version bullet shows a claim without a grep already drifted.
- Process-only ADRs in this range (ADR-0080 on reconciling forward-looking
  prose of the since-deleted `docs/roadmap/plano-testes-unitarios.md`;
  ADR-0083 on queueing dropped edits; ADR-0065 review-dedup meta; ADR-0073
  boundary-move definition of done) carried no architectural decision and are
  retired by this consolidation pass with no successor beyond this note and
  the matching note in ADR-0122.
