# ADR-0032: Pattern across the five raised issues: four of the five converge on o...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: Pattern across the five raised issues: four of the five converge on one root cause — MidiExporter was specified as 'mirror VgmExporter' and the mirroring was applied uniformly, without asking on which axes a MIDI score and a register log actually behave alike. Mirroring the static-singleton ownership and the Start/Stop/IsRecording surface was correct; mirroring produced a mismatch on the activation contract (raw tap vs. Enhanced-Audio-gated), on I/O strategy (stream-as-you-go vs. buffer-and-back-patch), and on the timebase, and it left a copied-in unused <chrono> include as residue. When a spec names a sibling as the template, it should name the axes to copy and the axes to decide independently; otherwise every axis where the two genuinely differ resurfaces later as a separately-reported issue, which is exactly the shape of this run's issue list.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
