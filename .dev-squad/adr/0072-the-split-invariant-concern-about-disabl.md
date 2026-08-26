# ADR-0072: The 'split invariant' concern about DisabledPackList.Set versus EmuAp...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during auditor-b: The 'split invariant' concern about DisabledPackList.Set versus EmuApi.SetMepPackEnabled is largely already discharged: the file header names EnhancementPackConfig.SetPackEnabled as the paired owner of the native sync, there is exactly one caller, and the pure-half/impure-shell split is the explicit strategy the whole test plan is built on. Treat this as accepted design rather than debt. The only durable takeaway for later phases is a placement convention — a pure helper that is one half of a stateful operation should stay as narrowly visible as the dual-compile allows and should name its impure partner in the header (as this one does), rather than each extraction re-litigating ownership.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
