# ADR-0080: Process pattern worth more than any single issue: issues 1 and 3 are ...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: none — process lore about a plan document deleted in 3587721e; no successor

## Context
Raised during auditor-b: Process pattern worth more than any single issue: issues 1 and 3 are the same finding surfaced twice (decompose + Execute/T1), and BOTH inherited a factually wrong premise from one line of stale plan prose — `docs/roadmap/plano-testes-unitarios.md:234` still reads "O job novo `unit-tests.yml` é o que falta hoje", written before Fase 0 delivered that file. The Fase 4 closeout commits (955b0e40, 9f6fcd75) updated the status header and the Fase 4 section but left the forward-looking "what's missing" prose untouched, and two independent critics then recommended creating a file that has existed for three phases. Lesson: a phase closeout must reconcile the plan's forward-looking sections (CI table, "o que falta hoje", roadmap ordering), not only its own phase heading — and a critic recommendation that merely restates a plan's own gap claim should be checked against the repo before it is accepted as a finding. Same-issue duplication across phases also inflates the apparent issue count: five reported issues are really three distinct concerns.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
