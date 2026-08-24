# ADR-0026: MIDI capture and VGM capture now have divergent activation contracts:...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during Execute/T2: MIDI capture and VGM capture now have divergent activation contracts: the VGM tap works from the raw register writes regardless of user settings, while MidiExporter::LogFrame is reachable only from inside each wrapper's `cfg.EnableEnhancedAudio` branch. A user who starts 'Record Music (MIDI/VGM)' without Enhanced Audio enabled for the active console silently gets a valid-but-empty .mid alongside a fully-populated .vgm, with no feedback distinguishing that from a bug. The spec explicitly accepts this as a v1 limitation and MidiExporter.h documents it honestly, so this is not a defect in T2 — but the two-exporters-one-button UI of F1.3 is where the divergence becomes user-visible.

## Decision
Non-blocking follow-up: have the combined Record Music action check the active console's EnableEnhancedAudio at start time and surface a one-line notice (MessageManager) when MIDI capture will be empty, rather than restructuring the gate itself.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
