# ADR-0103: palettes_per_shape is len(keys)/len(shapes) — a ratio that rises when...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0132

## Context
Raised during decompose: palettes_per_shape is len(keys)/len(shapes) — a ratio that rises whenever key count grows, including for PaletteColors values that differ only in bits the renderer never uses. Adopting it as the headline before/after metric for this fix risks reading a cosmetic key-count increase as genuine visual palette coverage.

## Decision
Alongside palettes_per_shape, report the distinct-variant distribution (max and histogram of variants per shape) for both sides, so the evidence shows whether variants concentrate on real multi-palette shapes rather than spreading thinly across all of them.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
