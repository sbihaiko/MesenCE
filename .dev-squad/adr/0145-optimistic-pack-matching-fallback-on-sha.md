# ADR-0145: Optimistic pack matching fallback on SHA1 mismatch: textures + BPS auto-apply, IPS stays gated

- Status: accepted
- Date: 2026-08-31

## Context
MEP/HD Pack currently requires exact No-Intro SHA1 match (ADR-0003, ADR-0039) to apply a pack. This blocks legitimate near-matches (e.g. same game, different dump/region) from auto-installing even when applying anyway is safe or self-validating. Key evidence: patches apply only in-memory (VirtualFile::ApplyPatch, VirtualFile.cpp:297-322) and are never written to disk — re-applied fresh from the original .nes on every load — so there is no permanent-corruption risk from an optimistic attempt, only a bad runtime session. BpsPatcher.cpp embeds and validates source+output CRC32 in the BPS format itself (returns false and refuses to apply on any mismatch). IpsPatcher.cpp has zero validation (only checks the "PATCH" header magic, no checksum of source or output, always returns true if the format parses), so mismatched-ROM IPS application produces silently-accepted garbage bytes with no detection point. HdNesPack already matches per-tile by pixel hash (HdTileKey), not by ROM identity; a non-matching tile silently falls through to the original NES tile. Alternatives considered: full backup-and-restore of the ROM file before patching (rejected — unnecessary since disk is never touched); relaxing IPS too (rejected — no output validation exists, silent garbage is worse than refusing).

## Decision
Relax the mandatory-exact-match gate scoped by content type: (1) HD textures apply optimistically on SHA1 mismatch — no corruption risk since HdNesPack falls through to the original tile on a non-match; promote the existing bg-tile-match-rate diagnostic (HdNesPack.cpp _debugBgTileLookups/_debugBgTileMatches) into a runtime health signal to warn/auto-disable when match rate stays low. (2) BPS patches apply optimistically on SHA1 mismatch — the format already self-validates via embedded CRC32 and refuses bad applies, so this is safe without new work. (3) IPS patches do NOT relax — keep exact SHA1 required until a manifest field for expected output hash is added (spec bump) to give IPS the same self-validation BPS already has. (4) Audio/MEP fingerprint replacement is out of scope for this ADR — keep requiring exact match (offsets/timing are calibrated per-ROM). Consequences: catalog/local packs for a near-matching ROM (same game, different dump/revision) can now apply textures and BPS patches without an exact SHA1 hit; IPS-only packs remain blocked on mismatch until output-hash validation lands. This amends the scope of ADR-0003/ADR-0039 (exact-match contract) for texture and BPS-patch application specifically — the No-Intro SHA1 hash contract and computation itself are unchanged, only the mandatory-block behavior on mismatch is narrowed by content type.

## Consequences


## Alternatives

