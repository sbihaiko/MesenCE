# ADR-0096: Promoting the ADR-0051 spike (failed outright on 6 of 12 tested ROMs) into an in-process, breakpoint-driven live feature reachable from an emulator shortcut is a design/reliability trade-off.

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0135

## Context
Raised during decompose

## Decision
Record an ADR deciding the probe's failure contract (explicit opt-in wording, hard time/instruction budget, guaranteed no-op on unsupported ROMs) and whether it runs on the emulation thread or a snapshot.

## Consequences


## Alternatives

