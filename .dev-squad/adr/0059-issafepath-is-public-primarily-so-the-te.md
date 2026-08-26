# ADR-0059: IsSafePath is public primarily so the test suite can drive the fixtur...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during Execute/T3: IsSafePath is public primarily so the test suite can drive the fixture directly and so a later task can reuse it; Validate is the only production consumer today. This widens the extracted module's public contract for test visibility, which sets the precedent for the rest of UI/Logic/ as Fase 2 adds more extracted types.

## Decision
Record in UI/AGENTS.md whether UI/Logic/ types may expose helpers publicly for direct unit-testing, or whether tests should go through the single entry point only — so MepPackListParser and the Fase 2 extractions follow one rule rather than being decided case by case.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
