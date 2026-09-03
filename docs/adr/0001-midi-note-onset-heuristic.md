# ADR-0001: MIDI note-onset/offset heuristic is an explicit, documented decision

- Status: accepted
- Date: 2026-08-24

## Context
Raised during spec: EnhancedSynthEngine::Input is a per-flush continuous frequency/volume snapshot per voice, not discrete note-on/off events with duration. Turning this into a correct SMF note stream (as F1.2 and the PRD's own MuseScore success criterion require) needs a note-segmentation/onset-detection layer (deciding when a sustained frequency/volume constitutes a new note vs. a held note) that does not yet exist anywhere in the tap the spec cites as '~90% done'. This is a real design gap the actor must resolve, and the AC-6 grep for 'class MidiExporter' cannot catch it.

## Decision
Define and document (e.g. in a short design note or code comment in MidiExporter.h) an explicit note-onset/offset heuristic — such as retriggering a note on a volume-envelope attack edge or a frequency jump beyond a pitch-bend threshold — before wiring MidiExporter to EnhancedSynthEngine::Input, so this becomes a deliberate, reviewable decision rather than an implicit one discovered mid-implementation.

**Resolved by:** the heuristic is documented in the onset-detection comment block of `Core/Shared/Audio/MidiExporter.h` (around line 45). A Note-On fires in exactly one of two cases: (1) "Volume-attack-from-silence" — `vol > kOnsetVolThreshold && lastVol <= kOnsetVolThreshold`, reusing the 0.001 threshold of `EnhancedSynthEngine::Retrigger`; (2) "Pitch-jump-with-hysteresis" — a sounding voice whose pitch moves by more than `kPitchJumpCents` (50) plus `kPitchJumpHysteresisCents` (15) from the held note is treated as Note-Off + Note-On rather than a continuous bend. No separate ADR records the values; the header comment is the normative description.

## Consequences
The musical correctness of every MIDI export hinges on this heuristic; making it explicit lets it be reviewed and tuned instead of reverse-engineered from output files. Interacts with the timing contract in ADR-0013 (tick positions) and the Enhanced Audio dependency in ADR-0014 (whether the snapshot is built at all).

## Alternatives
Emit one note per flush snapshot (no segmentation): produces an unreadable stream of 179 notes/second. Infer notes offline in a post-processing pass: moves the problem out of the emulator but doubles the format surface.
