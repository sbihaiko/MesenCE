# ADR-0117: Confirmed cross-console debt that will keep costing on every future M...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0136

## Context
Raised during auditor-b: Confirmed cross-console debt that will keep costing on every future MEP task: scripts/mep_compare.py is structurally NES-only while the repo's only checked-in golden MEP texture pack is GB. render_original (line ~108) does `bytes.fromhex(chr_hex)` on 32-hex CHR data and slices an 8-hex NES palette through NES_PALETTE, but docs/specs/golden/mep/textures/hires.txt declares `<system>gb` — so the comparator raises a bare ValueError inside a list comprehension when pointed at the project's own fixture. That already forced this run to hand-roll a private fixture instead of reusing the golden, and it will force the same duplication every time. Now that the product line is NES/GB/SMS/GBA after the core cut, the fix is a system dispatch in render_original with an explicit unsupported-system error, or a small NES-shaped golden that mep_compare tests can share.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
