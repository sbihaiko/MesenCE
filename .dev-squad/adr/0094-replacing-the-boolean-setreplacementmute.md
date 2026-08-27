# ADR-0094: Replacing the boolean SetReplacementMute(bool) with a per-channel SetReplacementMuteMask changes a core audio API contract in the NES mixer hot path (Bloco C), with no ADR recording the decision.

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0133

## Context
Raised during decompose

## Decision
Draft an ADR (id above 0091) covering the Bloco C contract: mask semantics, whether the boolean setter is kept as a deprecated shim or removed, and who owns the music/SFX split (ChannelRoleClassifier vs. the mixer).

## Consequences


## Alternatives

