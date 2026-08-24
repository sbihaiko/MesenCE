# ADR-0033: MidiExporter I/O — keep in-memory track buffers, open/validate the output stream at recording start

- Status: accepted
- Date: 2026-08-24

## Context
Raised during Execute/T1 and auditor-b (consolidates audit-round ADR-0025 and ADR-0029, ids from the reused 0022–0032 range): MidiExporter buffers the whole capture in memory (vector<uint8_t> _trackData[3]) and only touches the filesystem in WriteFile(), called from the destructor — diverging from VgmExporter, which opens its ofstream in the constructor and streams as it goes. The audit inverted the priority the raw finding gave the two consequences. The weak half is crash-durability: long captures ending in a kill are rare, and per-track delta back-patching is precisely what the SMF multi-track layout needs, so the in-memory buffers are a deliberate trade-off, not an oversight. The sharp half is failure silence: WriteFile opens the ofstream inside the destructor and, on failure, returns without writing or reporting anything (MidiExporter.cpp:158-161), so an unwritable path destroys the entire capture with no user-facing signal at any point — not even at StartRecording, where the path is never validated.

## Decision
Keep the in-memory track buffers (the SMF layout needs them). Do only the cheap half of the remedy: open/validate the ofstream in the MidiExporter constructor the way VgmExporter does, so StartRecording fails loudly on a bad path, and surface a WriteFile failure via MessageManager instead of returning silently. Skip periodic flushing of completed tracks.

## Consequences
An unwritable path is detected before any capture effort is spent, and a late write failure is at least visible. The ~10-line cost lands in a file with no headroom — sequence this after (or together with) the SMF byte-writer split in ADR-0034. Broader guidance feeding ADR-0035: 'mirror the sibling class' is sound for API surface and ownership, wrong for I/O strategy when the two formats have different structural needs.

## Alternatives
Mirror VgmExporter's streaming ofstream fully: breaks per-track back-patching, forcing a two-pass or seek-heavy writer. Add periodic flushing for crash-durability: real complexity spent on the rare half of the problem.
