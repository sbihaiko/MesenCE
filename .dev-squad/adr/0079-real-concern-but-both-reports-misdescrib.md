# ADR-0079: Real concern, but both reports misdescribe the fix: `.github/workflow...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0126

## Context
Raised during auditor-b: Real concern, but both reports misdescribe the fix: `.github/workflows/unit-tests.yml` ALREADY EXISTS (added in Fase 0 — `ubuntu-latest`, `setup-dotnet 10.x`, `dotnet test UI.Tests`). The gap is not a missing workflow, it is a missing second step in an existing job. Issue 3's suggested action ("add the unit-tests.yml workflow the plan calls for, on macOS/Linux") would either duplicate the existing file or silently rewrite Fase 0's job. Correct fix is ~4 lines: append a `run: make core-unit-tests` step to the existing `ui-tests` job (or a sibling job in the same file). This is the highest-priority item in the set — `core-unit-tests` is the only harness target with no `core` prerequisite, so it needs no MesenCore.dylib, no SDL2, and no ROM corpus. One caveat neither critic raised: the target compiles `Core/Shared/Audio/ChannelRoleClassifier.cpp`, `Core/Shared/EnhancementPacks/MepPack.cpp` and three `Utilities/*.cpp` with the host `$(CXX)`, and has only been exercised on macOS — verify the standalone compile on Linux before wiring it in, or the new step becomes a red CI on first push for a toolchain reason rather than a regression.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
