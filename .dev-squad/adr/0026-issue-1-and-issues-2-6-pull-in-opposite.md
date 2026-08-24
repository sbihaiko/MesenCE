# ADR-0026: Issue 1 and issues 2/6 pull in opposite directions and the tension mu...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: Issue 1 and issues 2/6 pull in opposite directions and the tension must be resolved explicitly rather than by whichever task lands last. Issue 1 wants the hot-path check to be a single cheap flag read; issues 2/6 want the exporter reached through the owning Emulator (_console->GetSoundMixer()->...), which is a multi-hop pointer chase on that same path. Both are right about their own axis. The reconciling shape is a per-console cached raw pointer or relaxed atomic flag held by the chip object itself, refreshed when recording starts/stops — emulator-scoped ownership with a single-load hot path. Deciding this before the remaining console wiring is what keeps it a one-time change.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
