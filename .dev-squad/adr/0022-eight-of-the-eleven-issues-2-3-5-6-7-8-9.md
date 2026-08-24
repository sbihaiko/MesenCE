# ADR-0022: Eight of the eleven issues (2, 3, 5, 6, 7, 8, 9, 10) are not independ...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: Eight of the eleven issues (2, 3, 5, 6, 7, 8, 9, 10) are not independent findings — they are one spec-level decision reported eight times. The task briefs for T1/T2 mandated a 'self-contained static-instance API, no plumbing through SoundMixer/Emulator', and that single constraint mechanically produces all of: process-global ownership, no per-Emulator lifecycle, no cross-producer locking, and no timestamp parameter (which in turn forces steady_clock in VgmExporter::EmitWait and the hardcoded FlushRateHz=179.0 in MidiExporter). Treat it as one decision to revisit, not eight defects to patch. The reviewing loop re-derived the same structural item per task instead of escalating it once — when the same root cause appears in three consecutive task reviews, it should be promoted to a spec change rather than re-litigated downstream.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
