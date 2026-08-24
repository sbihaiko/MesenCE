# ADR-0029: Nothing in this set is noise, but the set is badly deduplicated: issu...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: Nothing in this set is noise, but the set is badly deduplicated: issues 8 and 9 are the same finding stated twice with the same remedy, and 2/6/7/10 are one finding stated four times. Recommended order of attention: (1) timing source — 3/5/8/9, contract-shaped, cheapest now at six call sites; (2) issue 4 — user-visible, small; (3) ownership plus locking plus teardown — 2/6/7/10, at minimum documented and enforced; (4) hot-path guard and buffering — issue 1, including the false header claim; (5) issue 11 — decide and record. Items 1 through 3 should land before the F1.3 UI action makes the feature reachable by users, because each of them changes what a produced file means rather than merely how it is produced.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
