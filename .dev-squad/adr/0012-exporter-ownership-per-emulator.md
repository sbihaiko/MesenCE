# ADR-0012: VGM/MIDI exporters are owned per-Emulator (WaveRecorder pattern), not process-global singletons

- Status: accepted
- Date: 2026-08-24

## Context
Raised during decompose, Execute/T1, Execute/T2 and auditor-b (consolidates former ADR-0016, ADR-0017, ADR-0020, ADR-0022, ADR-0024): The T1/T2 task briefs mandated a 'self-contained static-instance API, no plumbing through SoundMixer/Emulator', and that single constraint mechanically produced a whole cluster of findings — the audit counted the same root cause reported as eight of eleven review issues across three consecutive task reviews. The concrete consequences, confirmed in code: (a) both VgmExporter and MidiExporter are file/class-scope static safe_ptr singletons, while every other recorder is emulator-scoped (WaveRecorder via SoundMixer, AviRecorder via VideoRenderer, MovieRecorder via MovieManager); (b) two concurrent consoles — VS DualSystem sub-console (commit 0155e22f), Super Game Boy, RecordedRomTest, netplay/history-viewer instances — interleave into one stream with no attribution; (c) recording state survives ROM load/unload and reset with no defined behaviour; (d) no lock protects the mutation of _stream/_lastEventTime/_trackData/_tickAccumulator — safe_ptr only makes acquiring the pointer safe, never the call, and this applies to VgmExporter::LogWrite just as much as MidiExporter::Log; (e) the no-timestamp signatures forced the timing defects handled in ADR-0013.

## Decision
Move ownership to SoundMixer/Emulator (safe_ptr member, mirroring _waveRecorder), reached through a thin static accessor / the existing console pointer so the chip write-sites written in AC-3/4/5 do not need to change; start/stop follows the WaveRecord/WaveStop lifecycle and Emulator/ROM-unload teardown calls StopRecording(). If the static facade is temporarily kept for expedience, the minimum acceptable version is: document the single-active-console contract in both headers, have teardown call StopRecording(), and either enforce a single-producer contract explicitly or add a lock around Log()/Stop() keying voice state per console tag. Do not ship the current state where the contract is neither enforced nor written down. This must land before the F1.3 UI action makes the feature reachable by users.

## Consequences
Resolves lifetime finalization and cross-thread access in one move; captures become attributable per instance. Hot-path cost of emulator-scoped access is resolved by ADR-0011's cached per-console flag. Process lesson for the workflow: when the same structural finding recurs across consecutive task reviews, promote it to a spec change instead of re-litigating it downstream.

## Alternatives
Keep the process-global singleton with a documented single-emulator contract (defers multi-instance correctness, does not solve attribution or lifecycle). Add locking to the global (fixes races but not attribution or reset/unload semantics).
