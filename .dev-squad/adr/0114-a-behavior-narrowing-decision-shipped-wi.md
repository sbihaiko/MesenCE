# ADR-0114: A behavior-narrowing decision shipped with no ADR, and the ADR it cla...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during auditor-b: A behavior-narrowing decision shipped with no ADR, and the ADR it claims to implement does not contain the step it cites. I read .dev-squad/adr/0050-auto-screen-backgrounds.md end to end: it is entirely about `<background>` screen capture and contains no 'step (b)', no palette-variant capture item, and no mention of a per-shape cap. The 'ADR-0050 step (b)' framing exists only in the plan file. Meanwhile the actual decision that shipped — a hard 32-variant-per-shape ceiling that bounds bootstrap fidelity — is recorded only inside a 5213-character single-line `**Status:**` header (line 3 of plano-execucao-F5.md) carrying measurement data, dead-code analysis and cap rationale. That header is now factually correct (commit fdd9d9d4 fixed it), so this is not a truth problem but a placement problem: decisions of this weight got ADRs in ADR-0050/0051/0052 and this one did not, and load-bearing rationale in an unsearchable mega-line will not survive contact with F5.4c/F5.4d.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
