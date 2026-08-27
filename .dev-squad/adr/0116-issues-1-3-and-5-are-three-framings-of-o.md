# ADR-0116: Issues 1, 3 and 5 are three framings of one real concern — the cap is...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during auditor-b: Issues 1, 3 and 5 are three framings of one real concern — the cap is silent, order-dependent, and untunable — and should have been ranked once, not thrice. Verified in CaptureOrCapPaletteVariant (HdPackBuilder.cpp:129-140): on saturation the code bumps usage on `variants.back()`, i.e. the most recently captured variant, with no log, no pack-side marker, and no palette-proximity or usage-frequency selection. Which 32 palettes survive is purely encounter order. Practical severity is low because 32 sits above the measured p99 of 27, so only the degenerate near-blank tail is bounded — the YAGNI argument against promoting the cap to HdPackBuilderOptions (issue 1) holds for now. The part worth doing immediately is the observability half of issue 3: one core log line the first time a shape saturates, so headless evidence can distinguish 'the game has N palettes' from 'the builder stopped at N'. Without it, F5.4c/F5.4d coverage reporting has no way to detect that the cap is biting.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
