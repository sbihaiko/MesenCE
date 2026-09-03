# ADR-0003: ROM hash contract — No-Intro byte range per console, string format pinned to observed utility output

- Status: accepted
- Date: 2026-08-24

## Context
Raised during spec and decompose (consolidates former ADR-0009): Two halves of the same hash contract were left unstated. (1) Byte range: the PRD's own 4.1 table names rcheevos `rhash` specifically for hash computation when the system hashes only part of the file (e.g. NES iNES headers and other header/trainer-bearing formats where No-Intro hashes only the ROM payload). The approved spec computes CRC32/SHA-1 via the existing utilities but does not specify whether hashing happens on the raw loaded file or on a header-stripped payload matching No-Intro's convention — hashing the wrong range makes MEP/MEI pack matching silently fail against real No-Intro-keyed packs even though the code builds and the ACs pass. (2) String format: the hash-string contract (hex case, byte order, CRC32-vs-SHA1 field naming) is frozen in the golden files by T2/T4 before any code has run against the real Utilities/CRC32 and Utilities/sha1 output; the plan's only mitigation ('flag it rather than silently editing the frozen golden') defers a contract break to the end of the run.

## Decision
Confirm and document (in MEP-v1.md/EnhancementPackManager) exactly which byte range is hashed per console, matching No-Intro's own convention — tracing how VirtualFile::GetSha1Hash() is already used in the codebase rather than assuming. Derive the golden hash strings from actual output of the existing utilities (e.g. VirtualFile::GetSha1Hash and CRC32 over a known file) at authoring time, so the spec is pinned to observed behaviour rather than an assumed format.

## Consequences
Pack matching works against real No-Intro-keyed packs on headered systems, and the goldens are authoritative from day one instead of authoritative-but-possibly-wrong until the end of the run.

## Alternatives
Hash the raw loaded file (simpler, but silently wrong for headered formats). Keep assumed-format goldens with flag-on-mismatch (defers the break and leaves a wrong golden authoritative in the meantime).
