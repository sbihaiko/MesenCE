# ADR-0015: Command timing is derived from std::chrono::steady_clock wall-clock d...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during Execute/T1: Command timing is derived from std::chrono::steady_clock wall-clock deltas rather than from the emulated master clock / sample counter. Every other VGM logger (and the VGM format itself) is defined on emulated-sample time, so any deviation between host time and emulation time — fast-forward, rewind, pause at a breakpoint, save-state load, frame-rate limiter off, a stalled host frame — writes wait values that do not correspond to the music that was actually produced. The tempo of a captured track becomes a function of host performance rather than of the game. The trade-off is deliberate and documented (it is what keeps LogWrite a zero-plumbing one-liner), but it materially changes what the exported file means, and the spec's own success criterion (F1.1 output opening correctly in vgmrips/foobar2000 tooling) is timing-sensitive.

## Decision
Keep the plumbing-free call signature, but source time from the emulated clock instead of the host clock: have VgmExporter hold a weak reference to the active Emulator (or accept an optional sample-count setter that SoundMixer/the console's audio flush updates ~179Hz, the same cadence the Enhanced Synth already runs at) and compute waits from that counter, falling back to steady_clock only if no clock source has been registered. This preserves the one-liner at chip write-sites while making captures cycle-faithful and immune to fast-forward/pause.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
