# ADR-0075: path-cases.txt becomes a shared contract fixture consumed by three in...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0124

## Context
Raised during decompose: path-cases.txt becomes a shared contract fixture consumed by three independent readers: the Fase 1 C# suite, scripts/validate-specs.py, and now the C++ core_unit_tests. That is the stated intent ("Divergência C#/C++ aparece como falha em uma das suítes"), but no doc currently records that the file is multi-consumer, so a future edit to add a case can silently break a suite the editor did not know existed.

## Decision
Record the consumer list for the golden MEP fixtures in docs/AGENTS.md (or a docs/specs/golden/AGENTS.md child), so anyone editing path-cases.txt knows all three suites must be re-run.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
