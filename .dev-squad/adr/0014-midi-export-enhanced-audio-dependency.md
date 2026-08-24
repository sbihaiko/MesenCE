# ADR-0014: MIDI export's dependency on EnableEnhancedAudio is decided explicitly before the F1.3 menu action ships

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose and confirmed by auditor-b (consolidates former ADR-0027): T4 says the wrappers feed 'their already-built EnhancedSynthEngine::Input snapshot ... on every MixAudio flush whenever MIDI recording is active', but Core/NES/EnhancedSynth.cpp:93-104 returns before building the snapshot whenever cfg.EnableEnhancedAudio is false (the GB/SMS wrappers mirror this, and the early-return also covers run-ahead frames). Since MidiExporter::LogFrame is fed exactly that snapshot, a user who wants a MIDI transcription but leaves Enhanced Audio off — a plausible default — gets a silently empty file with no error. This is the only user-visible functional gap in the audit set and the cheapest to fix.

## Decision
Decide the dependency explicitly before the F1.3 menu action ships: either build and feed the Input snapshot whenever MIDI recording is active even with the synth disabled (skipping only Render()), or make the dependency explicit by gating/labelling the menu action and documenting it in MidiExporter.h. In either case keep the IsRunAheadFrame() exclusion so replayed frames are not double-logged.

## Consequences
No silently-empty exports. The snapshot-always option costs snapshot construction during recording even with the synth off; the gating option costs a UI dependency users must understand.

## Alternatives
Ship as-is and document in release notes: users hit an empty-file failure with no feedback, violating the MuseScore success criterion for the most likely default configuration.
