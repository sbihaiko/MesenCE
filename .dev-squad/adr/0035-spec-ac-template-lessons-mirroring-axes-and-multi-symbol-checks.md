# ADR-0035: Spec/AC template lessons — name the mirroring axes, verify enumerated deliverables with multi-symbol checks, never reuse ADR ids

- Status: accepted
- Date: 2026-08-24

## Context
Raised during auditor-b (consolidates audit-round ADR-0022, ADR-0031 and ADR-0032, ids from the reused 0022–0032 range): three process findings from the F1 audit. (1) Issue 1 was noise as stated — RecordApi.cs already contains all six DllImport bindings (MidiRecord/MidiStop/MidiIsRecording/VgmRecord/VgmStop/VgmIsRecording), and a missing extern would fail the P/Invoke at first call and be caught by the required full build — but it exposed a real AC-template weakness: when a deliverable enumerates N symbols in one file, an AC that greps for one of them (AC-13 greps only `MidiRecord`) verifies that the file exists, not that the deliverable is complete. (2) Four of the run's five raised issues converge on one root cause: MidiExporter was specified as 'mirror VgmExporter' and the mirroring was applied uniformly, without asking on which axes a MIDI score and a register log actually behave alike — ownership and the Start/Stop/IsRecording surface mirrored correctly, while the activation contract (raw tap vs. Enhanced-Audio-gated, ADR-0014), the I/O strategy (stream vs. buffer-and-back-patch, ADR-0033) and the timebase (ADR-0013) each resurfaced later as separately-reported issues. (3) Discovered during this consolidation: adr.js assigns ids as max-existing+1, so deleting consolidated raw findings freed ids 0022–0032 and the next audit round reissued them, silently corrupting every 'consolidates former ADR-XXXX' reference in ADR-0011 through ADR-0021.

## Decision
Retrofit into the templates, not into this run: (1) when a deliverable enumerates N symbols in one file, the AC uses a count-based or multi-symbol check instead of a single representative grep; (2) when a spec names a sibling class as the template, it names the axes to copy and the axes to decide independently; (3) when consolidating ADRs, replacement ADRs take fresh ids beyond the highest id ever used (never delete-then-create, which reissues the freed ids), and consolidated files are deleted only after the replacements exist. Complements the lesson already recorded in ADR-0012: a structural finding recurring across consecutive task reviews is promoted to a spec change, not re-litigated downstream.

Historical note (accepted damage): ids 0009–0010, 0015–0020 and 0022–0032 are permanently retired — each names one or two deleted findings — and must never be reissued; the surviving "consolidates former ADR-XXXX" references in ADR-0011 through ADR-0021 are annotated with the round they belong to.

## Consequences
Single-grep ACs stop passing on incomplete deliverables; sibling-mirroring specs stop generating one late-reported issue per genuinely-different axis; ADR cross-references stay unambiguous across consolidation rounds.

## Alternatives
Fix only this run's ACs and spec text: the next run regenerates the same three failure shapes from the same templates.
