# ADR-0076: `core-unit-tests` is not wired into any aggregate target or CI workfl...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0126

## Context
Raised during Execute/T1: `core-unit-tests` is not wired into any aggregate target or CI workflow, so nothing runs it automatically — it only executes when a human types `make core-unit-tests`. The plan itself names this gap ("O job novo `unit-tests.yml` é o que falta hoje") and lists both `make unit-tests` and `make core-unit-tests` as the two no-core commands a PR should gate on. Left as-is, the phase ships a green test binary that cannot fail a PR.

## Decision
Add the `unit-tests.yml` workflow the plan calls for, running both `make unit-tests` and `make core-unit-tests` on macOS/Linux, so the framework-free suites actually gate changes. Track it as its own task rather than expanding T1.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
