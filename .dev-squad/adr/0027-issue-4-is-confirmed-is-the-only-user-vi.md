# ADR-0027: Issue 4 is confirmed, is the only user-visible functional gap in the ...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: Issue 4 is confirmed, is the only user-visible functional gap in the set, and is the cheapest to fix — it deserves attention out of proportion to its position in the list. Core/NES/EnhancedSynth.cpp:93-104 returns before building the EnhancedSynthEngine::Input snapshot whenever cfg.EnableEnhancedAudio is false (GB/SMS wrappers mirror this). Since MidiExporter::LogFrame is fed exactly that snapshot, a user who wants a MIDI transcription but leaves Enhanced Audio off — a plausible default — gets a silently empty file with no error. Decide the dependency explicitly before the F1.3 menu action ships: either build the snapshot when MIDI recording is active and skip only Render(), or gate/label the menu item and state the dependency in MidiExporter.h. Keep the IsRunAheadFrame() exclusion in either case so replayed frames are not double-logged.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
