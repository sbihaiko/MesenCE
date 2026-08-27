# ADR-0063: Issues 3 and 6 conflict and must be sequenced, not merged. Issue 3's ...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0123

## Context
Raised during auditor-b: Issues 3 and 6 conflict and must be sequenced, not merged. Issue 3's remedy is to demote the grep script to a fast pre-check and 'let the linked-compile failure in UI.Tests.csproj remain the authoritative gate' — but issue 6 demonstrates the linked compile is configured strictly weaker than the real UI build, so it cannot bear that authority as it stands. Issue 3's underlying technical claim is also half-wrong in the reassuring direction: it worries the grep misses a transitive dependency introduced via a `using` of another UI namespace, but the dual-compile *does* catch exactly that (no `ProjectReference` to UI.csproj means the type simply does not resolve). The grep is the weak link, not the compile. Resolution order: fix the csproj property parity first, then it is correct to name the compile the contract and the grep a pre-check — and only then is issue 3's suggested allowed-dependency list (BCL + System.IO.Compression) documentation rather than enforcement.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
