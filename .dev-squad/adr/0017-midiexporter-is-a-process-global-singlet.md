# ADR-0017: MidiExporter is a process-global singleton, whereas every other recor...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during Execute/T2: MidiExporter is a process-global singleton, whereas every other recorder in this codebase (WaveRecorder via SoundMixer, AviRecorder via VideoRenderer, MovieRecorder via MovieManager) is owned by an Emulator-scoped component. A process-global means all Emulator instances share one exporter — relevant because this repo already runs more than one console instance at a time (the VS DualSystem sub console, per commit 0155e22f, and the RecordedRomTest harness), so a second instance's LogFrame() would interleave into the same track buffers, and recording state would survive across ROM loads/unloads. The task brief did specify a 'self-contained static-instance API', so this is a spec-level decision rather than an implementation slip, but it is worth recording as a deliberate trade-off before the console wrappers (AC-9) are built on top of it.

## Decision
Either keep the static facade but document that it is single-emulator-only and have Emulator teardown call StopRecording(), or move ownership to SoundMixer/Emulator (safe_ptr<MidiExporter> member, thin DllExport passthrough) to match the WaveRecorder pattern — which would also resolve both blocking issues (lifetime finalization and cross-thread access) for free.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
