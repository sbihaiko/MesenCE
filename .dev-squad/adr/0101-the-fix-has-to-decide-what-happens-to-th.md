# ADR-0101: The fix has to decide what happens to the pre-existing `DefaultTile` ...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during decompose: The fix has to decide what happens to the pre-existing `DefaultTile` wildcard entry once real palette variants are captured for the same shape: keep it as a permanent fallback alongside the variants, or stop writing it once N real variants exist. That choice changes what a bootstrap pack looks like on disk (hires.txt gains both a wildcard line and per-palette lines for the same shape) and how the draw-time exact-key-then-wildcard resolution in HdNesPack.cpp:501/509 behaves for palettes never seen during recording. It should be an explicit, recorded decision rather than an implementation side effect.

## Decision
Keep the wildcard entry as the never-seen-palette fallback and add real palette-specific entries beside it, documenting this two-layer contract (wildcard = ROM-export ramp, exact keys = observed palettes) as an amendment to ADR-0050.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
