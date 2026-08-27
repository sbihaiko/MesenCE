# ADR-0102: The variant ceiling is introduced as a hardcoded internal constant wi...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during decompose: The variant ceiling is introduced as a hardcoded internal constant with no way to observe or tune it, while the target it is calibrated against (ADR-0050's ~7.6 palettes/shape from Zelda Remastered) is a directional figure. A long bootstrap session on a palette-heavy title will silently hit the cap and start dropping variants with no signal in the pack or the log, and the only feedback loop is re-running mep_compare.py by hand.

## Decision
Pick the cap from the ADR-0050 reference figure with headroom (e.g. 8-16) and emit a one-line core log message the first time a shape saturates it, so headless runs and mep_compare evidence can distinguish 'game really has N palettes' from 'builder stopped at N'.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
