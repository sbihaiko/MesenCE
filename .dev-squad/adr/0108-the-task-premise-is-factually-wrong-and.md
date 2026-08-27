# ADR-0108: The task premise is factually wrong, and the delivered change is ther...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0132

## Context
Raised during Execute/T1: The task premise is factually wrong, and the delivered change is therefore not the change the goal describes. I verified on base eaa36dad that `_tileUsageCount` is only ever written with `GetKey(false)` keys (AddTile line 102), while `GetKey(true)` sentinels PaletteColors to 0xFFFFFFFF - so the old 'DefaultTile wildcard' fallback at line 118 could never match and was dead code. ProcessTile ALREADY created a distinct HdPackTileInfo for every distinct (shape, PaletteColors) sighting; the measured pre-change median was 14 palettes/shape, already double ADR-0050's ~7.6 directional target. The net behavioural effect of this diff is therefore not a capture fix but a NEW 32-variant-per-shape ceiling that strictly reduces what the bootstrap captures relative to today. Consequence at runtime: palette combos beyond the 33rd for a shape now fall through HdNesPack's exact-key-then-wildcard lookup to un-enhanced NES rendering. That is a defensible trade (it bounds the degenerate blank-tile long tail the header comment measures at 71 variants), and the spec did explicitly ask for the cap - but F5.4b should be recorded as 'bounded per-shape growth', not 'fixed a wildcard collapse', or the roadmap/ADR will carry a false account of what step (b) was.

## Decision
Accept the cap but re-scope ADR-0050 step (b) and the plano-execucao-F5.md header wording to 'bound per-shape palette-variant growth' rather than 'fix the DefaultTile funnel'. Also reconsider whether a flat numeric cap is the right instrument versus skipping near-blank/low-entropy shapes explicitly, since the header comment identifies flat tiles - not real palette diversity - as the actual source of the long tail.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
