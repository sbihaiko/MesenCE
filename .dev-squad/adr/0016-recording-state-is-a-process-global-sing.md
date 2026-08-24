# ADR-0016: Recording state is a process-global singleton rather than per-Emulato...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during Execute/T1: Recording state is a process-global singleton rather than per-Emulator state, unlike the sibling WaveRecorder which lives on SoundMixer and is therefore scoped to an emulator instance. Mesen runs more than one console concurrently in real configurations (VS DualSystem's sub-console — see commit 0155e22f, Super Game Boy, netplay/history-viewer secondary instances), and every one of those will funnel its chip writes into the same single VGM stream with no way to attribute or separate them. The task JSON explicitly asked for the self-contained static API to avoid plumbing, so this is an accepted constraint rather than a mistake, but it is a contract decision that the per-console wiring tasks (AC-3/4/5) will bake in at every write-site.

## Decision
Document the single-active-console limitation in the header now, and if multi-instance capture matters later, move ownership to SoundMixer (mirroring _waveRecorder) with a thin static accessor that resolves the emulator-owned instance, so the call sites written in AC-3/4/5 do not need to change.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
