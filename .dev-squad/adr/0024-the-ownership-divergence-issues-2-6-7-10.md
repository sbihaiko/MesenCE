# ADR-0024: The ownership divergence (issues 2, 6, 7, 10) is real and correctly d...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: The ownership divergence (issues 2, 6, 7, 10) is real and correctly diagnosed, but the practical risk is narrower than the write-ups imply and the mitigation should be sized accordingly. Confirmed: both exporters use a file/class-scope static safe_ptr, while WaveRecorder hangs off SoundMixer and AviRecorder off VideoRenderer. The concrete consequences are (a) two concurrent consoles interleave into one stream with no attribution, (b) recording state survives ROM load/unload and reset with no defined behaviour, and (c) neither LogWrite nor Log holds any lock across its mutation of _stream/_lastEventTime/_trackData/_tickAccumulator — safe_ptr::lock() only makes acquiring the pointer safe, never the call. Issue 10 raises (c) for MidiExporter only; it applies identically to VgmExporter::LogWrite, which no critic flagged. If the static facade is kept for expedience, the minimum acceptable version is: document the single-active-console contract in both headers, have Emulator/ROM-unload teardown call StopRecording(), and either enforce single-producer explicitly or add a lock. Do not ship the current state where the contract is neither enforced nor written down.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
