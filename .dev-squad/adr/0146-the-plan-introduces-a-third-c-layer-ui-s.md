# ADR-0146: The plan introduces a third C# layer (UI/Services/) whose dependency ...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during decompose: The plan introduces a third C# layer (UI/Services/) whose dependency boundary is defined only implicitly: UI/Logic must stay BCL-only (enforced by scripts/verify-ui-logic-firewall.sh, which greps UI/Logic/*.cs), UI/Services is allowed HttpClient + EmuApi + Avalonia, but nothing states or enforces the reverse direction (UI/Logic must never reference UI/Services, and network I/O must never drift back into UI/Logic or into UI/Windows code-behind). With the flow split across fetcher/coordinator/service, the temptation to put a quick HttpClient call in a window code-behind or a decision class is real and would pass every AC in this spec.

## Decision
Extend the existing firewall script (or add one guardrail) to assert the layering explicitly: UI/Logic/*.cs stays free of Avalonia/EmuApi/HttpClient and of any Mesen.Services reference, and HttpClient usage in UI/ is confined to UI/Services/ plus the pre-existing UpdatePromptViewModel; record the three-layer rule (Logic = host-free decisions, Services = host/network orchestration, Windows = presentation) in UI/AGENTS.md.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
