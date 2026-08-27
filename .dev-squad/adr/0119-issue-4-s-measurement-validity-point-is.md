# ADR-0119: Issue 4's measurement-validity point is real but largely self-resolve...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0132

## Context
Raised during auditor-b: Issue 4's measurement-validity point is real but largely self-resolved, and worth keeping only as a metric-hygiene rule. `palettes_per_shape` in scripts/mep_compare.py:215 is len(keys)/len(shapes), a ratio that rises with any key-count growth including PaletteColors bits the renderer never uses — so it cannot distinguish genuine visual coverage from cosmetic key inflation. In the end the evidence did not lean on it: validate_palette_variants.py reports max-variants-per-shape, shapes-above-1, and shapes-at-cap, which are distribution facts rather than a ratio. Rule to carry forward: for coverage claims, report the distribution (max, histogram, count at cap) rather than a mean or ratio, because a per-shape cap and a long degenerate tail both move a mean in misleading directions.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
