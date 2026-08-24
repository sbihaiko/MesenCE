# ADR-0025: MidiExporter buffers the whole capture in memory (vector<uint8_t> _tr...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during Execute/T1: MidiExporter buffers the whole capture in memory (vector<uint8_t> _trackData[3]) and only touches the filesystem in WriteFile(), called from the destructor. This diverges from the sibling it is documented as mirroring: VgmExporter opens its ofstream in the constructor and streams commands as they happen. Two consequences follow from the divergence rather than from any bug: (1) an emulator crash, kill, or power loss mid-capture loses 100% of the MIDI, where a VGM capture would retain everything written so far; (2) the output path is never validated at StartRecording time, so an unwritable filename is only discovered at stop, at which point the capture is already gone. The in-memory buffer is what makes the terse <=200-line writer possible (deltas can be back-patched per track, EOT appended at the end), so this is a real trade-off, not an oversight.

## Decision
Keep the in-memory track buffers (they are what the SMF multi-track layout needs), but open/validate the ofstream in the MidiExporter constructor the way VgmExporter does, so StartRecording fails loudly on a bad path; optionally flush completed tracks periodically if crash-durability is judged to matter for long captures.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
