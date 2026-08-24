# ADR-0023: One menu action starts two exporters with different capture precondit...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: One menu action starts two exporters with different capture preconditions: VgmExporter taps raw register writes and records regardless of settings, while MidiExporter::LogFrame is only reachable from inside each wrapper's `if(!cfg.EnableEnhancedAudio ...) return;` branch (Core/NES/EnhancedSynth.cpp:96, Core/Gameboy/GbEnhancedSynth.cpp:92, Core/SMS/SmsEnhancedSynth.cpp:96). A user who hits 'Record Music (MIDI/VGM)' without Enhanced Audio enabled for the active console gets a valid .vgm next to a header-only .mid, with no feedback distinguishing the two. The combined action also has to derive two filenames from a single prompt and has a mixed 'either is recording' Stop-enable predicate, so the UI can sit in a half-recording state with no way to see which half is live.

## Decision
Either surface the precondition at the point of action (disable/annotate the MIDI half, or warn once, when EnableEnhancedAudio is off for the active console), or make the two captures independently observable in the menu (per-format Record/Stop entries or a status label) instead of a single combined toggle whose two halves can silently disagree.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
