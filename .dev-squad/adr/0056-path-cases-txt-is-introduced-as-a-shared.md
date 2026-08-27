# ADR-0056: path-cases.txt is introduced as a shared fixture whose whole purpose ...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0124

## Context
Raised during decompose: path-cases.txt is introduced as a shared fixture whose whole purpose is to catch divergence between the C# MepZipValidator and C++ MepPack::NormalizeRelativePath (the plan notes they already diverge: the C++ side rejects control chars < 0x20 and ignores '.' segments, the C# side does not). Nothing in this slice enforces the `path<TAB>ok|bad` format or the file's existence, and its only consumer until Fase 4 is the C# suite — so the format can drift or the file can be silently reshaped before the second consumer ever reads it.

## Decision
Pin the contract at creation: a header comment in path-cases.txt stating the exact format and both intended consumers, plus a check in scripts/validate-specs.py (which already walks docs/specs/golden/) that every non-comment line matches `^[^\t]+\t(ok|bad)$`. Keeping it a plain fixture — not a new spec — is right; it just needs a cheap format guard.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
