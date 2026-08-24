# ADR-0027: Issues 2 and 5 are the same defect reported through two lenses (decom...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: Issues 2 and 5 are the same defect reported through two lenses (decompose-phase and execute-phase) and should be counted once, not twice — the raised count overstates its weight but the issue itself is the run's only genuinely user-visible one. Verified in code: MidiExporter::LogFrame is reachable only from inside each wrapper's cfg.EnableEnhancedAudio branch, while VgmRecord taps raw register writes unconditionally, so the single 'Record Music (MIDI/VGM)' action can produce a populated .vgm next to a 3-track header-only .mid with no signal that anything is wrong. Fix at the cheapest point: have the Record OnClick check the active console's EnableEnhancedAudio and emit one MessageManager notice — do not restructure the gate, and do not split the menu into per-format entries (the Record/Stop enable predicates are already complementary in practice, so the 'half-recording state' half of the concern is theoretical). While in that handler, note a second real hazard: both filenames are derived from one prompt via Path.ChangeExtension, so a ROM name containing a dot ('Zelda v1.2') silently truncates at the wrong separator for both files.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
