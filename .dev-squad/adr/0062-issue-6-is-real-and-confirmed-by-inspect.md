# ADR-0062: Issue 6 is real and confirmed by inspection: `UI.Tests/UI.Tests.cspro...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0123

## Context
Raised during auditor-b: Issue 6 is real and confirmed by inspection: `UI.Tests/UI.Tests.csproj` sets `ImplicitUsings=enable` and leaves `TreatWarningsAsErrors` unset, while `UI/UI.csproj` sets `TreatWarningsAsErrors=true` and does not set `ImplicitUsings` at all (grep returns zero matches). The two compilations of `UI/Logic/**/*.cs` therefore do not agree, and the dual-compile is the *looser* of the pair — so `dotnet test` passing does not imply the UI build passes, which is the exact inverse of what `UI.Tests/AGENTS.md` claims ('any accidental dependency breaks dotnet test immediately'). Blast radius is narrower than the issue implies, though: I built `UI/Logic/**` under a scratch csproj with `EnableDefaultCompileItems=false`, `TreatWarningsAsErrors=true` and ImplicitUsings off — 0 warnings, 0 errors, so nothing is broken today, and `build.yml`'s Windows `msbuild -t:UI` would catch a regression eventually. The cost is a green ubuntu `unit-tests` job followed by a red Windows build, plus a documented guarantee that is currently false. Two lines in the test csproj make the claim honest; this is the cheapest high-value fix of the nine.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
