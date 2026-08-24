# ADR-0012: T1/T2 specify a self-contained static-instance (singleton) API explic...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: T1/T2 specify a self-contained static-instance (singleton) API explicitly to avoid plumbing through SoundMixer/Emulator, which diverges from how every other recorder in this codebase is owned: WaveRecorder hangs off SoundMixer and is reached via _emu->GetSoundMixer(), AviRecorder via _emu->GetVideoRenderer(). A process-global exporter has no owning emulator instance, which matters here because this repo already runs two console instances at once (see commit 0155e22f, 'don't create a second enhanced synth for the VS DualSystem sub console') — both instances' register writes would land in one file. It also leaves reset/load-state/unload lifecycle and thread-safety (the emulation thread writes, the UI thread starts/stops) undefined, and puts a global-state read on NesApu::WriteRam / GbApu::Write, which are on the hot I/O path.

## Decision
Own the exporters from SoundMixer (or Emulator) the way WaveRecorder is owned, and reach the chip write-sites through the existing console pointer, so start/stop follows the same lifecycle as WaveRecord/WaveStop and the instance is scoped to one emulator. If the singleton is kept for expedience, document the multi-instance and threading behaviour in the header and make the hot-path check a single relaxed atomic bool load.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
