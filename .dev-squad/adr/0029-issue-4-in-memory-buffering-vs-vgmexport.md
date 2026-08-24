# ADR-0029: Issue 4 (in-memory buffering vs. VgmExporter's streaming ofstream) is...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: Issue 4 (in-memory buffering vs. VgmExporter's streaming ofstream) is real but its priority should be inverted from how it was framed. Crash-durability is the weak half — long emulator captures that end in a kill are rare, and per-track back-patching is what the SMF layout needs. The sharp half is failure silence: MidiExporter::WriteFile opens the ofstream in a destructor and, on failure, returns without writing or reporting anything (MidiExporter.cpp:158-161), so an unwritable path destroys the entire capture with no user-facing signal at any point. Do only the cheap half: open/validate the stream in the MidiExporter constructor as VgmExporter does, so StartRecording fails loudly. Skip periodic flushing. The broader lesson: 'mirror the sibling class' is sound guidance for API surface and ownership, and wrong guidance for I/O strategy when the two file formats have different structural needs — the spec should say which axes of a sibling to mirror.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
