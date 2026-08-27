# ADR-0068: Extracting only the list-mutation half of SetPackEnabled leaves the i...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0127

## Context
Raised during decompose: Extracting only the list-mutation half of SetPackEnabled leaves the invariant split across two files: DisabledPackList.Set owns the in-memory list state, while EnhancementPackConfig still owns keeping the native core in sync via EmuApi.SetMepPackEnabled. A future caller can reach DisabledPackList.Set directly and silently desynchronise the config list from the core.

## Decision
Document in DisabledPackList's file-header comment that it is the list-mutation half of EnhancementPackConfig.SetPackEnabled and must not be called without the paired native sync — or, if this pattern recurs in later phases, record an ADR for how extracted pure helpers signal that they are only one half of a stateful operation.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
