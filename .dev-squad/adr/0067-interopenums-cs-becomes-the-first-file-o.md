# ADR-0067: InteropEnums.cs becomes the first file outside UI/Logic/ that is dual...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0123

## Context
Raised during decompose: InteropEnums.cs becomes the first file outside UI/Logic/ that is dual-compiled into the host-free test assembly, but the firewall script only enforces host-freedom over UI/Logic/*.cs. Nothing stops a future edit from adding a DllImport, an Avalonia using, or another P/Invoke struct to InteropEnums.cs (it sits in UI/Interop/, where that is the norm), which would break `dotnet test` on a machine without the native core and only be caught at CI build time rather than by the named guardrail.

## Decision
Either extend verify-ui-logic-firewall.sh to also scan every path the csproj dual-compiles (deriving the list from the <Compile Include> entries rather than hardcoding UI/Logic), or establish the convention that host-free shared types live in a dedicated folder the firewall already covers. Worth an ADR since it defines where the host-free/host-bound boundary lives as more types get extracted in later phases.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
