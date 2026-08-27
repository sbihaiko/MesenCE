# ADR-0066: Issues 9 and 8 are both small placement/consistency questions and sho...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0122

## Context
Raised during auditor-b: Issues 9 and 8 are both small placement/consistency questions and should be handled in one documentation pass, not as separate workstreams. On 9: this repo has a real ADR register at `.dev-squad/adr/` (0045-mep-layers, 0046-mep-provenance, 0048-human-authoring-layout exist) and `UI/Logic/MepZipValidator.cs` itself cites ADR-0049 — so a durable, cross-cutting trade-off like 'UI.Tests permanently outside the solution-level restore and format gates' sitting only in a directory AGENTS.md is inconsistent with how this project records exactly that class of decision. On 8: `IsSafePath` is public at `UI/Logic/MepZipValidator.cs:65` while `Validate` is the sole production consumer, and `UI/AGENTS.md`'s Work Guidance is silent on whether UI/Logic/ types may widen their public surface for direct unit-testing. At two extracted types this is trivial; the reason to settle it now is that Fase 2 adds several more and will otherwise decide case by case. Neither is urgent on its own — both are cheap while the surface is small.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
