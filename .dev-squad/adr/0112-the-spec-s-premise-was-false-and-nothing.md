# ADR-0112: The spec's premise was false, and nothing in the pipeline caught it b...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: none — process lessons (defect-fix specs carry a reproduction; unverified critic issues are unranked); retired as ADRs, see ADR-0132 Alternatives

## Context
Raised during auditor-b: The spec's premise was false, and nothing in the pipeline caught it before six architecture concerns were raised against it. I confirmed the claim of critics 7/9/11: `HdTileKey::GetKey(true)` sentinels `PaletteColors` to `0xFFFFFFFF` (Core/NES/HdPacks/HdData.h:23-32) while `_tileUsageCount` is only ever written with `GetKey(false)` keys (HdPackBuilder.cpp:102) — so the 'DefaultTile wildcard funnel' the spec was written to fix was unreachable dead code, and per-(shape,palette) capture was already working and unbounded (measured 182 shapes, median 14 variants, one shape at 71). The delivered diff is therefore not a capture fix but a new 32-variant-per-shape ceiling that strictly reduces capture relative to base. Process lesson: a spec whose objective is 'fix defect X' must carry a reproduction of X (a failing check, a log line, a measured number) before Spec/Decompose runs; a ten-minute read of two files would have voided this task's entire premise and the five follow-on ADR candidates derived from it.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
