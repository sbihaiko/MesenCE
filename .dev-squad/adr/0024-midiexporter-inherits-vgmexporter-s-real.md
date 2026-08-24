# ADR-0024: MidiExporter inherits VgmExporter's real-time std::chrono cadence as ...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: MidiExporter inherits VgmExporter's real-time std::chrono cadence as its musical timebase, but the two uses are not equally forgiving. For VGM the drift only shifts sample waits; for MIDI it maps directly onto note durations and the tempo track, so a PAL/GB/SMS capture (or any fast-forward, pause-at-breakpoint, or save-state load during recording) yields a score whose note lengths are systematically wrong when opened in a notation editor — which is precisely the PRD's stated success criterion. The plan documents this rather than correcting it, which is a reasonable slice boundary, but it makes the header's honesty note the only defense.

## Decision
Keep the nominal cadence for this slice, but isolate it behind a single tick-source seam in MidiExporter (one function converting elapsed real time to MIDI ticks) so a later slice can swap in an emulated-clock/sample-count source for all three consoles without touching the note state machine or the SMF writer.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
