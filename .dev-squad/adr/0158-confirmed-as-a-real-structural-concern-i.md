# ADR-0158: CONFIRMED as a real structural concern (issues 4 and 5 are duplicates...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during auditor-b: CONFIRMED as a real structural concern (issues 4 and 5 are duplicates of each other — count them once). `scripts/verify-ui-logic-firewall.sh` enforces exactly one direction: UI/Logic/*.cs must not reference Avalonia or EmuApi. Nothing states or enforces what UI/Services may depend on, that UI/Logic must never reference Mesen.Services, or that HttpClient stays out of UI/Logic and UI/Windows code-behind. The evidence that this is not hypothetical is in this very run: decision logic (the container-name rule, finding above) drifted out of UI/Logic on the *first* Services file that existed. Write the three-layer rule into UI/AGENTS.md (Logic = host-free decisions, Services = host/network orchestration, Windows = presentation) and add the inverse grep to the existing script. This is the moment to pin it — the layer is one file old.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
