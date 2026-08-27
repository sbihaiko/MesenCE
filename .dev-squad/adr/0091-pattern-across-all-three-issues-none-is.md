# ADR-0091: Pattern across all three issues: none is a code defect — every one is...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0131

## Context
Raised during auditor-b: Pattern across all three issues: none is a code defect — every one is a contract-vs-reality drift in .github/AGENTS.md, the same failure class this task was created to clean up (stale plano-testes-unitarios.md references). The root cause is that the guardrails are written in terms of specific tool names ('it must never require the native InteropDLL/MesenCore build or SDL2', 'if a future UI.Tests addition needs either') rather than invariants, so they go stale the moment a lane gains a step of a different kind. A second instance is already present and unnoticed by the critics: .github/AGENTS.md says the `dotnet-version` value should track dotnet-format-check.yml's, 'currently 10.0.x', but unit-tests.yml:24 pins `10.x` (build.yml also uses `10.x`). Prefer writing CI contracts as invariants plus a grep-able Verification line — the existing Verification block is what kept the `make core-unit-tests` claim honest, and the version bullet has no such check.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
