# ADR-0031: Issue 1 is noise as stated and should not consume remediation budget:...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: Issue 1 is noise as stated and should not consume remediation budget: RecordApi.cs already contains all six DllImport bindings, both MidiRecord and VgmRecord, and a missing extern would fail the P/Invoke at first call and be caught by the full build the plan already requires. The generalizable process lesson is still worth keeping: when a deliverable enumerates N symbols in one file, an AC that greps for one of them verifies the file exists rather than that the deliverable is complete. Prefer a count-based or multi-symbol check over a single representative grep — but retrofit that convention into the AC template, not into this run.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
