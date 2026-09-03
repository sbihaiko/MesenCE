# ADR-0127: Extracted pure helpers name their stateful partner in the file header

- Status: accepted (record of fact — `UI/Logic/DisabledPackList.cs` already follows it; adopted as the convention for future extractions)
- Date: 2026-08-27
- Consolidates: ADR-0068, ADR-0072

## Context
Phase 2 extracted only the list-mutation half of
`EnhancementPackConfig.SetPackEnabled` into `UI/Logic/DisabledPackList.Set`
(case-insensitive de-duplication of `DisabledPacks`), leaving the other half —
keeping the native core in sync via `EmuApi.SetMepPackEnabled` — in
`EnhancementPackConfig`. ADR-0068 flagged the split invariant: a future caller
could reach `DisabledPackList.Set` directly and desynchronise the config list
from the core.

ADR-0072 found the concern largely discharged: the file header of
`UI/Logic/DisabledPackList.cs` reads "Host-free counterpart to
EnhancementPackConfig.SetPackEnabled's list mutation ... The caller
(EnhancementPackConfig.SetPackEnabled) still owns the EmuApi.SetMepPackEnabled
native call - this only mutates the list."; there is exactly one caller; and
the pure-half/impure-shell split is the explicit strategy the whole unit-test
plan is built on (host-free logic under `UI/Logic/`, dual-compiled into
`UI.Tests`). What survives is a placement convention so later extractions do
not re-litigate ownership.

## Decision
When a pure helper under `UI/Logic/` is one half of a stateful operation, its
file header comment must name the impure partner that owns the other half
(the method that performs the side effect, e.g. the `EmuApi` call) and state
that the helper only performs its pure part. The helper stays as narrowly
visible as the dual-compile allows (see ADR-0125 for the public-surface rule)
and gains no side effects of its own. `DisabledPackList.cs` is the reference
example.

## Consequences
- Readers of a `UI/Logic` helper can find the side-effecting counterpart
  without searching call sites; the invariant is documented at the point most
  likely to be edited.
- Enforcement is by review and by the extraction's definition of done, not by
  tooling; the firewall script (ADR-0123) does not check headers.
- No code change is required today. Future extractions of half-operations
  (e.g. any further `EnhancementPackConfig` or ViewModel splits) must add the
  header line in the same commit.
- If the number of such split helpers grows, consider promoting the convention
  into `UI/AGENTS.md` Work Guidance as a one-line bullet.

## Alternatives
- Keep the invariant whole by not extracting `Set` (leave list mutation inside
  `EnhancementPackConfig`): rejected — defeats the purpose of the host-free
  extraction, which is to unit test the de-duplication without `EmuApi`.
- Have `DisabledPackList.Set` perform the native sync itself: rejected —
  reintroduces the `EmuApi` dependency the `UI/Logic` firewall forbids.
- Treat the split as debt requiring a follow-up ADR per extraction (ADR-0068's
  second branch): rejected per ADR-0072 — this single convention covers the
  recurring case.
