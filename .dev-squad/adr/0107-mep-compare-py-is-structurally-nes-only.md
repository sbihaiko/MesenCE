# ADR-0107: mep_compare.py is structurally NES-only (32-hex CHR shape + 8-hex NES...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during Execute/T2: mep_compare.py is structurally NES-only (32-hex CHR shape + 8-hex NES palette) yet the repo's only checked-in golden MEP texture pack, docs/specs/golden/mep/textures, is GB-shaped - so the comparator crashes with a raw ValueError on the project's own fixture. That forced this task's fixture-based check to hand-roll its own pack instead of reusing the golden, and it will force the same duplication on every future mep_compare test.

## Decision
Either give render_original an explicit system/palette-width dispatch (nes 8-hex vs gb/sms 4-hex) with a clear unsupported-system error instead of a ValueError deep in a list comprehension, or add a small NES-shaped golden under docs/specs/golden/mep/ that mep_compare tests can share.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
