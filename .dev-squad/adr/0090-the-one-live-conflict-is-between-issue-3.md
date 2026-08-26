# ADR-0090: The one live conflict is between issue 3 and issues 1/2: issue 3 want...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during auditor-b: The one live conflict is between issue 3 and issues 1/2: issue 3 wants a compiler matrix inside the step, while issues 1/2 both rest on keeping this lane a single cheap signal (and issue 1 objects specifically to extra compile time riding along with the C# tests). Resolve it in favour of 1/2 — document the clang-only choice instead of expanding the matrix. Nothing here warrants immediate attention; all three are documentation edits to .github/AGENTS.md that can ride the next touch of that file.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
