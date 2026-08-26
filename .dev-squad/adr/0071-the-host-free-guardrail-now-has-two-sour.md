# ADR-0071: The host-free guardrail now has two sources of truth: UI.Tests.csproj...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during auditor-b: The host-free guardrail now has two sources of truth: UI.Tests.csproj's <Compile Include> entries define what is actually dual-compiled, while verify-ui-logic-firewall.sh hardcodes UI/Logic as the scanned set. Fase 2 made those diverge (InteropEnums.cs is compiled but not scanned) and later phases will add more entries, so the divergence will widen silently. Derive the scanned paths from the csproj's Compile Include list instead of hardcoding the folder. The actual blast radius is modest — an Avalonia/DllImport addition there still breaks `dotnet test` compilation for everyone immediately, just with an opaque 'namespace not found' error instead of the firewall's explanatory one — so this is a diagnostics/maintenance fix, not a correctness hole, and it does not warrant an ADR in a repo that keeps no ADR directory.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
