# ADR-0074: The new `core-unit-tests` target is a regression gate that nothing ru...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0126

## Context
Raised during decompose: The new `core-unit-tests` target is a regression gate that nothing runs automatically — confirmed that .github/workflows/ references none of the existing harness targets (`roles-probe`, `capture-tool`, `spike-sound-driver`) either, so Bloco A/B assertions only protect the code when a human remembers to invoke them. Fase 4 doubles the number of hand-run C++ checks without deciding where they get enforced.

## Decision
Decide (in a follow-up, not this phase) whether `core-unit-tests` joins CI as the first non-ROM C++ check. It is the only harness target with no `core` prerequisite, so it needs neither MesenCore.dylib nor a ROM corpus — making it the cheapest candidate for a real CI job, and a natural companion to the Fase 0-3 `dotnet test` harness.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
