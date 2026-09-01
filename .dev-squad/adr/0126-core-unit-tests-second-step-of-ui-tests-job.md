# ADR-0126: C++ core-unit-tests runs as a second step of the ui-tests job (no new job)

- Status: accepted (record of fact — already reflected in `.github/workflows/unit-tests.yml`)
- Date: 2026-08-27
- Consolidates: ADR-0074, ADR-0076, ADR-0079, ADR-0085 (rejected per ADR-0088)

## Context
Phase 4 of the unit-test plan added `scripts/core_unit_tests.cpp`, a
framework-free C++ harness (ChannelRoleClassifier, `MepPack::NormalizeRelativePath`
/ `MepPack::Parse`, later `FindFallbackSubfolder` and `DetectConventionLayout`
via ADR-0120/0121), built by the makefile target `core-unit-tests`
(makefile target `core-unit-tests`). Unlike `roles-probe`, `capture-tool` and `spike-sound-driver`,
that target has no `core` prerequisite: it compiles
`scripts/core_unit_tests.cpp`, `Core/Shared/Audio/ChannelRoleClassifier.cpp`,
`Core/Shared/EnhancementPacks/MepPack.cpp` and three `Utilities/*.cpp` with the
host `$(CXX)` (`-std=c++17 -O2 -w`), links no MesenCore/SDL2, needs no ROM
corpus, and runs the binary. It was therefore the cheapest candidate for the
first non-ROM C++ check in CI (ADR-0074), and until wired in it was a
regression gate nothing ran automatically (ADR-0076).

ADR-0076 proposed adding a new `unit-tests.yml` workflow, inheriting a stale
line from the plan doc ("the new unit-tests.yml job is what is missing today").
ADR-0079 corrected this: `.github/workflows/unit-tests.yml` already existed
since Phase 0 (`ubuntu-latest`, `setup-dotnet` `10.x`, `dotnet test
UI.Tests/UI.Tests.csproj`), so the gap was a missing step, not a missing file,
and the fix was to append `run: make core-unit-tests` to the existing
`ui-tests` job after verifying the standalone compile on Linux. ADR-0085 then
worried that one job coupling dotnet and a C++ compiler blurs the pass/fail
signal; ADR-0088 rebutted that GitHub attributes failures to the named step,
and the added cost is one `clang++` invocation over six translation units.

State at HEAD: the `ui-tests` job has steps "Checkout repo", "Install .NET",
"Run unit tests" (`dotnet test UI.Tests/UI.Tests.csproj --nologo`) and
"Run core unit tests" (`make core-unit-tests`). No second job, no matrix.

## Decision
The C++ harness runs as the step `Run core unit tests` (`make core-unit-tests`)
inside the existing `ui-tests` job of `.github/workflows/unit-tests.yml`, after
the `dotnet test` step. No new workflow file and no separate job or matrix
entry is created for it. Failure attribution relies on the step name.

## Consequences
- Both host-free suites (C# and C++) gate every push/PR to `main` in one cheap
  ubuntu job; no MesenCore build, no SDL2, no ROM corpus involved.
- The job id `ui-tests` is now narrower than its content; the naming/contract
  drift is handled in ADR-0131 (invariant wording in `.github/AGENTS.md`), not
  by renaming or splitting the job.
- The C++ step is gated on the makefile's default `CXX := clang++` only; the
  clang-only choice and gcc coverage are recorded in ADR-0131.
- The step runs from the checkout root, which satisfies the harness's
  cwd-relative golden paths (ADR-0129).
- A C++ compile failure fails the whole job run, so contributors iterating on
  C# tests also wait for the C++ compile (seconds). Accepted.

## Alternatives
- Add a new `unit-tests.yml` workflow running `make unit-tests` +
  `make core-unit-tests` on macOS/Linux (ADR-0076): rejected per ADR-0079 —
  the file already existed; this would duplicate or silently rewrite the
  Phase 0 job.
- Defer the CI decision to a later phase (ADR-0074): superseded — done in the
  same clean-up pass once the Linux compile was confirmed.
- Second job or matrix entry with its own `name:` for the C++ harness
  (ADR-0085): rejected per ADR-0088 — the named step already distinguishes the
  C#-vs-C++ signal, and a second job would duplicate checkout/setup for a
  sub-minute compile. Remains a known option if the harness grows.
