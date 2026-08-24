# ADR-0018: MIDI tick position is derived from a hard-coded nominal cadence (Flus...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during Execute/T2: MIDI tick position is derived from a hard-coded nominal cadence (FlushRateHz = 179.0) rather than from elapsed emulated time, because the mandated LogFrame(consoleTag, presetId, const Input&) signature carries no timestamp. The real cadence is not 179 Hz everywhere: it is set by each console's PlayAudioBuffer rhythm (NES NTSC ~179 Hz, PAL ~149 Hz, and GB/SMS have their own rates). Any console/region whose actual flush rate differs from 179 Hz produces an export whose tempo is wrong by that ratio - a PAL NES capture would come out ~20% fast against the 120 BPM / 480 PPQN grid. The trade-off is documented honestly in the header, so this is a contract decision rather than an implementation slip, but it will surface as soon as later tasks wire GB/SMS or a PAL ROM into LogFrame().

## Decision
Extend the LogFrame() contract with an explicit time source (an elapsed-samples, or sampleRate + sampleCount, argument - every caller's MixAudio(out, sampleCount, sampleRate) already has it in hand) and derive ticks from measured time; keep FlushRateHz only as a fallback when the caller passes 0.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
