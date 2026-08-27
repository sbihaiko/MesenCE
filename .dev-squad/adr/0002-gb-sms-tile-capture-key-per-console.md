# ADR-0002: GB/SMS tile-capture identity key is a recorded per-console decision, not a 1:1 HdBuilderPpu port

- Status: accepted
- Date: 2026-08-24

## Context
Raised during spec: The spec assumes the NES HdBuilderPpu tile-capture pattern (extends NesPpu<HdBuilderPpu>, CRTP-style) ports directly to GbPpu and SmsVdp, but GB adds CGB palette layers/banking and SMS VDP has multiple tile/sprite modes not present on the NES PPU — structural differences the spec's own Risk Areas section already flags but does not resolve into a concrete per-console tile-identity/palette-key design.

## Decision
Treat the GB and SMS tile-capture key format (what uniquely identifies a 'tile' for dedup/replacement purposes, including palette/bank) as a decision the actor records explicitly per console during F2.1, rather than assuming a 1:1 structural port of HdBuilderPpu.

**Implemented by ADR-0036 (GB) and ADR-0037 (SMS)**, which record the actual per-console identity keys.

## Consequences
The key format determines pack compatibility forever after (it is what pack authors key their replacements on), so it must be right before the F2 hires.txt extension spec freezes. See ADR-0004 for the draft status of that spec.

## Alternatives
Port HdBuilderPpu structurally and patch the key format later: breaks every pack authored against the interim format.
