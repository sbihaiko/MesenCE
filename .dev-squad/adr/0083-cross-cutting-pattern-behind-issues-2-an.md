# ADR-0083: Cross-cutting pattern behind issues 2 and 5: Fase 4 shipped two known...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during auditor-b: Cross-cutting pattern behind issues 2 and 5: Fase 4 shipped two known gaps as prose rather than as mechanism or as tracked work. Both were scope-driven — 2fdd41a2 explicitly dropped the `.gitignore` edit to keep T1's branch clean, and c9d11911 corrected a doc that had falsely claimed the gitignore entry existed. Scope discipline and doc honesty both worked as intended; what is missing is the third step — nothing captured either dropped edit as a follow-up item, so "documented honestly" became the terminal state instead of an interim one. The debt is the absent follow-up queue, not the scope decisions. Practical guard: when a task drops an in-scope-adjacent edit, the closeout should record it in the plan's own pending list (the plan already has a DOX/pending section at lines 242-251) rather than only in the AGENTS.md of the affected directory, where it reads as a permanent contract.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
