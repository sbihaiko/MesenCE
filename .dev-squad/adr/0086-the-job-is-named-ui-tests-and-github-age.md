# ADR-0086: The job is named `ui-tests` and .github/AGENTS.md's guardrail frames ...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during decompose: The job is named `ui-tests` and .github/AGENTS.md's guardrail frames unit-tests.yml as the cheap C#/dotnet lane ("it must never require the native InteropDLL/MesenCore build or SDL2"). Adding a C++ compile-and-run step makes the job's name and its documented identity narrower than its actual content. The step does comply with the letter of the guardrail (the `core-unit-tests` target links only three named .cpp files plus Utilities, with no MesenCore/SDL2), but future readers will have no stated rule for what else may join this job — the guardrail's phrasing no longer distinguishes 'cheap native compile of listed sources' from 'full native build'.

## Decision
Keep the single-job approach the spec mandates, but when editing .github/AGENTS.md restate the guardrail in terms of the actual invariant rather than language ('no InteropDLL/MesenCore link, no SDL2, no platform SDK — a self-contained compile of explicitly listed sources is in scope'), and consider noting that the job now covers both suites despite its `ui-tests` id, so a later rename is a known, deliberate option rather than a surprise.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
