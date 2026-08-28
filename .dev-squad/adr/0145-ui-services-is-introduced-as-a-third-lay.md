# ADR-0145: UI/Services/ is introduced as a third layer with no declared boundary...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during decompose: UI/Services/ is introduced as a third layer with no declared boundary contract: UI/Logic is BCL-only and machine-enforced by scripts/verify-ui-logic-firewall.sh, UI/Windows is Avalonia, but nothing states what Services may depend on (HttpClient, EmuApi, Avalonia dialogs?) or forbids decision logic from migrating out of UI/Logic into it, where it would lose all test coverage.

## Decision
Document the Services boundary in UI/AGENTS.md (Services may use HttpClient/EmuApi/filesystem; all pure decisions stay in UI/Logic) and extend the firewall script with the inverse assertion that UI/Logic/*.cs never references System.Net.Http, so the boundary is enforced in both directions.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
