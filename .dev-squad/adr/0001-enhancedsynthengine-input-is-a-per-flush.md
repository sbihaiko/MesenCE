# ADR-0001: EnhancedSynthEngine::Input is a per-flush continuous frequency/volume...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during spec: EnhancedSynthEngine::Input is a per-flush continuous frequency/volume snapshot per voice, not discrete note-on/off events with duration. Turning this into a correct SMF note stream (as F1.2 and the PRD's own MuseScore success criterion require) needs a note-segmentation/onset-detection layer (deciding when a sustained frequency/volume constitutes a new note vs. a held note) that does not yet exist anywhere in the tap this spec cites as '~90% done'. This is a real design gap the actor will need to resolve, not something the AC-6 grep for 'class MidiExporter' will catch.

## Decision
Have the actor define and document (e.g. in a short design note or code comment in MidiExporter.h) an explicit note-onset/offset heuristic — such as retriggering a note on a volume-envelope attack edge or a frequency jump beyond a pitch-bend threshold — before wiring MidiExporter to EnhancedSynthEngine::Input, so this becomes a deliberate, reviewable decision rather than an implicit one discovered mid-implementation.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
