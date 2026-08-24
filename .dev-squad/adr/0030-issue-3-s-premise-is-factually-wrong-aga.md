# ADR-0030: Issue 3's premise is factually wrong against the shipped code and its...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: Issue 3's premise is factually wrong against the shipped code and its severity claim should be discounted before acting on it. MidiExporter does not inherit VgmExporter's std::chrono cadence: it uses a fixed kFlushRateHz = 179.0 constant with a carried fractional remainder, and the header says so explicitly. Because ticks advance per audio flush rather than per wall-clock interval, the specific failures the issue predicts — fast-forward, pause-at-breakpoint, save-state load during recording — do not distort note lengths at all; a per-flush timebase is strictly more correct for a musical score than the wall-clock source the critic assumed. The genuine residual is narrower: on PAL/GB/SMS the real flush cadence differs from the nominal 179 Hz, which scales the whole capture by a constant factor and is correctable by editing one tempo meta event. Adopt the suggested remedy anyway, because it is nearly free and repays other debt: extract the four inlined lines at MidiExporter.cpp:32-36 into the AdvanceTick() the header already claims exists. That creates the future swap-in seam and closes the doc/code drift in one edit.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
