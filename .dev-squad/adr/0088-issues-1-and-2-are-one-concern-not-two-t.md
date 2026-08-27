# ADR-0088: Issues 1 and 2 are one concern, not two: the `ui-tests` job now runs ...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0131

## Context
Raised during auditor-b: Issues 1 and 2 are one concern, not two: the `ui-tests` job now runs a second, non-dotnet suite, so its id and its AGENTS.md contract are narrower than its content. Real but low-cost debt — worth recording, not worth reopening ADR-0079. Two parts of issue 1 are overstated and should not drive a redesign: GitHub attributes a failure to the named step (`Run core unit tests`), so the C#-vs-C++ signal is already distinguishable in the UI, and the added cost is a single `clang++` invocation over 6 translation units with no SDL2/MesenCore link. The durable fix is the one issue 2 proposes: state the guardrail as an invariant (no InteropDLL/MesenCore link, no SDL2, no platform SDK; a self-contained compile of explicitly listed sources is in scope) and note in .github/AGENTS.md that the `ui-tests` id now covers both suites, so a later rename is a known option rather than a surprise. Defer any job/matrix split to a human decision.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
