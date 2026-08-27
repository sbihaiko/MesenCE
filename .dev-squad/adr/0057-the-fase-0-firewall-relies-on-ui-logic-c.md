# ADR-0057: The Fase 0 firewall relies on `UI/Logic/**/*.cs` being compiled twice...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0123

## Context
Raised during Execute/T1: The Fase 0 firewall relies on `UI/Logic/**/*.cs` being compiled twice, but the two compilations do not use the same C# property set. `UI.Tests.csproj` sets `ImplicitUsings=enable` and leaves `TreatWarningsAsErrors` unset; `UI/UI.csproj` does not enable `ImplicitUsings` and sets `TreatWarningsAsErrors=true`. A Logic file that omits an explicit `using System;` will compile green under `dotnet test` and fail the real UI build, and any warning in Logic code fails the UI build while `dotnet test` stays green. The dual-compile therefore does not actually prove what UI.Tests/AGENTS.md claims it proves ('any accidental dependency breaks dotnet test immediately'). This is latent today (no UI/Logic/ files exist yet) but bites the moment T2 lands MepZipValidator/MepPackListParser.

## Decision
Make the test project's compile-relevant properties a strict superset-in-strictness of UI.csproj's for the dual-compiled sources: drop `ImplicitUsings=enable` (or enable it in UI.csproj too) and add `TreatWarningsAsErrors=true` to UI.Tests.csproj. Record the rule in UI.Tests/AGENTS.md as 'properties affecting compilation of ../UI/Logic must stay at parity with UI/UI.csproj', so the firewall's guarantee is real rather than nominal.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
