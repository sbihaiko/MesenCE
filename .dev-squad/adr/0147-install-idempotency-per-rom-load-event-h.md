# ADR-0147: Install idempotency per ROM-load event has no defined key. The ROM-lo...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during decompose: Install idempotency per ROM-load event has no defined key. The ROM-load hook can fire repeatedly in one session (power-cycle, region switch, settings change), and the spec's own Risk Areas flag re-triggered consent dialogs and duplicate downloads, but no deliverable or AC pins down what makes a second attempt a no-op — the §43 reinstall gate keys on the installed .mep-install.json stamp's source.sha256, which is a filesystem fact, not a per-session guard.

## Decision
Decide and record the idempotency key: an in-memory per-session set of (rom sha1, catalog entry sha256) attempts short-circuited before any network call, with the .mep-install.json stamp remaining the cross-session gate.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
