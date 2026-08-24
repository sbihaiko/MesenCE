# ADR-0023: The timing defect (issues 3, 5, 8, 9) is the highest-priority item an...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: The timing defect (issues 3, 5, 8, 9) is the highest-priority item and should be fixed before any further wiring lands. It is confirmed in code: VgmExporter::EmitWait derives VGM waits from std::chrono::steady_clock deltas, and MidiExporter derives ticks from a hardcoded 179.0 Hz nominal cadence. Both make exported tempo a function of host performance and console/region rather than of the emulated music, which directly contradicts the PRD's own success criteria (file opens correctly in vgmrips/foobar2000; MIDI opens in MuseScore). Note that issues 3 and 5 propose incompatible remedies — a per-call masterClock argument versus a registered sample-count clock source. Pick one deliberately: the master-clock variant means three heterogeneous clock domains (NES 1.79MHz, GB 4.19MHz, SMS 3.58MHz) that each write-site must convert, whereas a SoundMixer-updated 44100Hz sample counter is uniform across all three consoles, matches the VGM timebase natively, and preserves the one-liner call sites. Every MixAudio(out, sampleCount, sampleRate) caller already has the value in hand. Cost of fixing now is six call sites; cost after F1.3 and the remaining console wiring is much higher.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
