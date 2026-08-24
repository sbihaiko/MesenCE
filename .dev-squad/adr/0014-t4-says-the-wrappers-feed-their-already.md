# ADR-0014: T4 says the wrappers feed 'their already-built EnhancedSynthEngine::I...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: T4 says the wrappers feed 'their already-built EnhancedSynthEngine::Input snapshot ... on every MixAudio flush whenever MIDI recording is active', but MixAudio returns early before the snapshot is built when cfg.EnableEnhancedAudio is false (also on run-ahead frames). As written, MIDI export would silently produce an empty file for any user who has Enhanced Audio turned off — a plausible default for someone who just wants to capture a MIDI transcription.

## Decision
Decide explicitly whether MIDI export requires Enhanced Audio: either build and feed the Input snapshot when MIDI recording is active even with the synth disabled (skipping only Render), or make the dependency explicit by gating/labelling the menu action and documenting it in MidiExporter.h. Either way, keep run-ahead frames excluded so replayed frames are not double-logged.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
