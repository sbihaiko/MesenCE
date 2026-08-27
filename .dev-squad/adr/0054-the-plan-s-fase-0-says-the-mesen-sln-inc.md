# ADR-0054: The plan's Fase 0 says the Mesen.sln inclusion question must be decid...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0122

## Context
Raised during decompose: The plan's Fase 0 says the Mesen.sln inclusion question must be decided before coding ("decidir antes de codar, nao depois"), because build.yml, tests.yml and dotnet-format-check.yml all run solution-level `dotnet restore -r win-x64 -p:PublishAot=...` and `dotnet format --verify-no-changes` on Windows. The task plan defers recording that decision to T5, after UI.Tests.csproj has already been written in T1 — so the csproj's shape (editorconfig/tabs conformance, whether a Build.0 entry is needed) is fixed before the decision that governs it. The spec also acknowledges the decision cannot be verified from this non-Windows environment.

## Decision
Record the decision as an ADR up front: keep UI.Tests.csproj OUT of Mesen.sln (unit-tests.yml invokes the csproj path directly, so nothing needs it in the solution), which keeps the RID-less, AOT-free test project entirely off the Windows solution-level restore/format paths. Revisit only if a future consumer needs solution-wide discovery, in which case include it with Build.0 disabled for Release|x64 and hold the test code to the .editorconfig tab style.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
