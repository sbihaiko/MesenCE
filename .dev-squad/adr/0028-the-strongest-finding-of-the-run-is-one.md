# ADR-0028: The strongest finding of the run is one no critic raised: the 200-lin...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: The strongest finding of the run is one no critic raised: the 200-line-per-file guardrail was satisfied by relocating prose rather than by decomposing, and it has now boxed the file in. MidiExporter.cpp sits at 198/200 lines with zero headroom, while MidiExporter.h is 163 lines that are mostly rationale comments. Both remediations the critics recommend (open/validate the ofstream in the constructor, extract a tick-source seam) add ~10 lines to a file that cannot take them, so the guardrail — not the design — will dictate the next change. The relocation has also already started to drift: the header's timing section says 'see AdvanceTick()' but no such member exists (the tick math is inlined at MidiExporter.cpp:32-36), and the header still includes <chrono> which the .cpp never uses. Treat 'move the prose to the header' as a one-time escape hatch that has been spent; the next edit should split the SMF byte-writer (WriteVarLen/AppendDelta/AppendBytes/EmitEvent/WriteFile) out of the note state machine, which both restores headroom and gives the rationale comments a file whose code they actually sit next to.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
