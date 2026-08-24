# ADR-0020: The exporter is a single process-wide static instance (`static safe_p...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during Execute/T2: The exporter is a single process-wide static instance (`static safe_ptr<MidiExporter> _instance`) with no internal lock protecting Log(). safe_ptr only makes acquiring the pointer safe; it does not serialize concurrent Log() calls. If two consoles ever feed the same instance — the VS DualSystem sub-console (cf. commit 0155e22f) or the SGB Gameboy running inside an SNES — Log() races on _trackData/_lastEventTick and double-advances _tickAccumulator, corrupting both the byte stream and the tempo grid.

## Decision
Either state and enforce a single-producer contract in the header (and have the downstream per-console wiring tasks honour it), or add a SimpleLock around Log()/Stop() and key voice state per console tag.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
