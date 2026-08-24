# ADR-0003: The PRD's own 4.1 table names rcheevos `rhash` specifically for 'cálc...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during spec: The PRD's own 4.1 table names rcheevos `rhash` specifically for 'cálculo do hash quando o sistema hasheia só parte do arquivo' (e.g. NES iNES headers, other header/trainer-bearing formats where No-Intro hashes only the ROM payload, not the loader header). The approved spec computes CRC32/SHA-1 via the existing utilities but does not specify whether hashing happens on the raw loaded file or on a header-stripped payload matching No-Intro's convention. If it hashes the wrong byte range for headered systems, MEP/MEI pack matching will silently fail against real No-Intro-keyed packs even though the code builds and the ACs pass.

## Decision
Have the actor confirm and document (in MEP-v1.md/EnhancementPackManager) exactly which byte range is hashed per console, matching No-Intro's own convention, before wiring pack lookup — this may already be implicit in how VirtualFile::GetSha1Hash() is used elsewhere in the codebase and should be traced rather than assumed.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
