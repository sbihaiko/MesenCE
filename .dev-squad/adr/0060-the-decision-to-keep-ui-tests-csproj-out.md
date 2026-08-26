# ADR-0060: The decision to keep UI.Tests.csproj out of Mesen.sln is recorded in ...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during Execute/T5: The decision to keep UI.Tests.csproj out of Mesen.sln is recorded in UI/AGENTS.md with rationale (as the task required), but it is a durable cross-cutting trade-off: the test project stays permanently outside the solution-level `dotnet restore -r win-x64 -p:PublishAot=true` and `dotnet format --verify-no-changes` gates, so UI.Tests code is never format-checked in CI and the RID-less-csproj-under-AOT-restore risk is deferred rather than resolved.

## Decision
Promote the UI/AGENTS.md paragraph to a numbered ADR (alongside ADR-0047/0049 already cited in the diff) so the re-evaluation trigger is explicit: revisit once a Windows runner can confirm the win-x64/AOT restore, or add the project with Build.0 disabled under Release|x64 plus an editorconfig/tabs pass.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
