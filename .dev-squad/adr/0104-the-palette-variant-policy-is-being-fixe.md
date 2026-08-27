# ADR-0104: The palette-variant policy is being fixed as a hard-coded internal co...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0132

## Context
Raised during decompose: The palette-variant policy is being fixed as a hard-coded internal constant (MaxPaletteVariantsPerTile) with an unspecified eviction/priority rule: once the cap is hit for a shape, later distinct palettes are silently dropped to usage-count-only, so which variants survive depends purely on encounter order during the recording session rather than on usage frequency or visual significance. For a bootstrap builder whose whole purpose is coverage, order-dependent truncation is a design trade-off worth recording (and revisiting in F5.4c/F5.4d, where pack size and UI coverage reporting become visible).

## Decision
Record the cap as a deliberate internal, order-first policy for F5.4b, and note the follow-up option of ranking variants by usage count (retaining the top-N most-used palettes per shape) if coverage evidence in F5.4c/F5.4d shows order-first truncation losing common palettes.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
