# ADR-0073: All three issues raised this run are instances of one pattern: an ext...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during auditor-b: All three issues raised this run are instances of one pattern: an extraction moved code across a boundary, but the artifact describing that boundary did not move with it — the firewall's scanned-path list, the ownership of a stateful invariant, and the exception contract of a formerly-private method. When a phase relocates code into the host-free/testable zone, treat 'update every guardrail, contract doc, and test that describes this boundary' as part of the extraction's definition of done, not as follow-up. Here the docs (UI.Tests/AGENTS.md, the plan's risk section) were updated correctly and only the executable check lagged, which is the right failure mode but still worth closing.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
