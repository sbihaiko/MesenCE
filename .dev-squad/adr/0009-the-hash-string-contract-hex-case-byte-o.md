# ADR-0009: The hash-string contract (hex case, byte order, CRC32-vs-SHA1 field n...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: The hash-string contract (hex case, byte order, CRC32-vs-SHA1 field naming) is frozen in the golden files by T2/T4 before any code has been run against the real Utilities/CRC32 and Utilities/sha1 output. The plan's mitigation is only 'flag it rather than silently editing the frozen golden', which defers a contract break to the end of the run and leaves the golden authoritative-but-possibly-wrong in the meantime.

## Decision
Have T2/T4 derive the golden hash strings from actual output of the existing utilities (e.g. via VirtualFile::GetSha1Hash and CRC32 over a known file) at authoring time, so the spec is pinned to observed behaviour rather than to an assumed format.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
