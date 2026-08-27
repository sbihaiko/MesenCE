# ADR-0109: `_paletteVariantsByShape` is not seeded from the existing on-disk hir...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0132

## Context
Raised during Execute/T1: `_paletteVariantsByShape` is not seeded from the existing on-disk hires.txt at construction (the ctor loads _hdData.Tiles and calls AddTile, which populates _tilesByKey/_tileUsageCount but not the new variant map). The header comment discloses this honestly, but it means MaxPaletteVariantsPerTile is a per-session bound, not a pack-level invariant: each re-record can add up to 32 more variants per shape on top of whatever is already on disk. The validator's 'no shape exceeds the cap' check consequently only holds for a fresh recording, and is not the structural guarantee it reads as.

## Decision
Seed _paletteVariantsByShape in the constructor from the loaded _hdData.Tiles (grouping non-DefaultTile entries by GetKey(true)) so the cap is a pack-level invariant, or state explicitly in the header comment and the validator docstring that the bound is per-session only.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
