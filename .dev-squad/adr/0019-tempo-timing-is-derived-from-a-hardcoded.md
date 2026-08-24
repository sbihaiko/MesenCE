# ADR-0019: Tempo/timing is derived from a hardcoded nominal cadence (FlushRateHz...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during Execute/T2: Tempo/timing is derived from a hardcoded nominal cadence (FlushRateHz = 179.0) rather than a measured delta, because LogFrame(consoleTag, presetId, Input) carries no timestamp. Whenever the real flush cadence differs from ~179Hz — different audio buffer size or sample rate, fast-forward/rewind, frame-rate changes, or a paused emulator — the exported MIDI's absolute timing drifts linearly from what was actually heard. This is documented as deliberate, but it directly affects the PRD's "opens correctly in MuseScore" success criterion.

## Decision
Extend the LogFrame signature with the sampleCount/sampleRate the wrapper already has in MixAudio (or an emulated-time stamp) and derive the tick delta from it, keeping FlushRateHz only as the fallback when no timing is supplied.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
