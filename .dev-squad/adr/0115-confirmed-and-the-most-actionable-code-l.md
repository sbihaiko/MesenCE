# ADR-0115: Confirmed and the most actionable code-level finding: state loaded fr...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during auditor-b: Confirmed and the most actionable code-level finding: state loaded from an existing on-disk pack is not rehydrated into the new tracking map, so the cap is a per-session bound masquerading as a pack invariant. The constructor (HdPackBuilder.cpp:35-52) loads hires.txt and calls AddTile for every tile, which populates `_tilesByKey`/`_tileUsageCount` but never `_paletteVariantsByShape`, so each re-record can add up to 32 more variants per shape on top of whatever is on disk. The header comment discloses this honestly, but scripts/validate_palette_variants.py and scripts/AGENTS.md both state 'no shape exceeds the cap' as a structural guarantee that only holds for a fresh recording. Note this is the second instance of the same defect class in this one file — `_screensSeen` has the identical gap — which makes it a pattern worth a rule: any new per-shape/per-screen tracking map in HdPackBuilder must be seeded in the constructor from `_hdData` or explicitly documented as session-scoped at every place its bound is asserted.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
