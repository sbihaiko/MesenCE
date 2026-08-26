# ADR-0055: The firewall relies on a shell grep (scripts/verify-ui-logic-firewall...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during decompose: The firewall relies on a shell grep (scripts/verify-ui-logic-firewall.sh) plus the dual-compile trick to keep UI/Logic/*.cs host-free. The spec's own risk section notes that a future helper needing a UI-side type breaks the firewall silently until dotnet test runs, and grep for 'Avalonia'/'EmuApi' will not catch a transitive dependency introduced through a using of another UI namespace.

## Decision
Treat UI/Logic/ as a named boundary in UI/AGENTS.md with an explicit allowed-dependency list (BCL + System.IO.Compression only), and let the linked-compile failure in UI.Tests.csproj remain the authoritative gate; the grep script is a fast pre-check, not the contract.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
