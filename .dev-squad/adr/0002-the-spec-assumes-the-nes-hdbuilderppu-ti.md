# ADR-0002: The spec assumes the NES HdBuilderPpu tile-capture pattern (extends N...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during spec: The spec assumes the NES HdBuilderPpu tile-capture pattern (extends NesPpu<HdBuilderPpu>, CRTP-style) ports directly to GbPpu and SmsVdp, but GB adds CGB palette layers/banking and SMS VDP has multiple tile/sprite modes not present on the NES PPU — structural differences the spec's own Risk Areas section already flags but does not resolve into a concrete per-console tile-identity/palette-key design.

## Decision
Treat the GB and SMS tile-capture key format (what uniquely identifies a 'tile' for dedup/replacement purposes, including palette/bank) as a decision the actor should record explicitly per console during F2.1, rather than assuming a 1:1 structural port of HdBuilderPpu.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
