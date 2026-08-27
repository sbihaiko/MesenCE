# ADR-0100: MaxPaletteVariantsPerTile is being added as a hardcoded builder-local...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during spec: MaxPaletteVariantsPerTile is being added as a hardcoded builder-local constant rather than a configurable HdPackBuilderOptions field, unlike Scale/FilterType which are already user-facing bootstrap options. If a fixed cap later proves wrong for some titles (too tight -> no-op fix, too loose -> pack bloat on long sessions), the ADR-0050 series may want it promoted to a tunable option in a future phase.

## Decision
Track as a candidate follow-up ADR: consider exposing the palette-variant cap as an HdPackBuilderOptions field (with the current constant as its default) once real-world bootstrap sessions show whether a fixed value is universally adequate.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
