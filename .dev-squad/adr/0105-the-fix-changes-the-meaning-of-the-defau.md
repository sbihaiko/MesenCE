# ADR-0105: The fix changes the meaning of the DefaultTile wildcard entry in buil...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0132

## Context
Raised during decompose: The fix changes the meaning of the DefaultTile wildcard entry in builder output: it stops being 'the one entry per shape' and becomes a fallback beside palette-specific entries. Whether the wildcard entry is kept (as a catch-all for palettes never seen, or seen past the cap) or promoted away is a contract decision between the builder and the existing exact-key-then-wildcard draw path — and it determines rendering behavior for unseen palettes.

## Decision
Keep the DefaultTile wildcard entry alongside the new palette-specific entries so unseen or past-cap palettes still render via the existing wildcard fallback, and state that invariant explicitly (builder emits: 0..N palette-specific entries + at most one wildcard per shape) so the loader/draw contract stays unchanged.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
