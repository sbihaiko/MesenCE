# ADR-0110: The new header clause records a material change to F5.4b's premise: i...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during Execute/T3: The new header clause records a material change to F5.4b's premise: it states that `HdPackBuilder::ProcessTile` already gave every distinct `PaletteColors` of a shape its own `HdPackTileInfo`, that the old `DefaultTile`/`GetKey(true)` wildcard fallback was dead code, and that the only thing actually shipped is the `MaxPaletteVariantsPerTile = 32` cap. I verified this against the code: `HdTileKey::GetKey(true)` sentinels `PaletteColors` to `0xFFFFFFFF` (Core/NES/HdPacks/HdData.h:23-32) while `_tileUsageCount` is only ever populated with real-palette `GetKey(false)` keys (HdPackBuilder.cpp AddTile), and no PPU palette word can be 0xFFFFFFFF. So the roadmap item that ADR-0050 sequenced as a capture-side fix turned out to need no fix, and F5.4b is now marked done on the strength of a bound plus a 'pre-existing, not regressed' measurement. That reversal currently lives only inside a parenthetical in a 7KB one-line header; the ADR/plan trail still frames F5.4b as a funnel fix.

## Decision
Amend ADR-0050 (or add a short superseding note) stating that step (b)'s funnel premise did not hold and that the delivered scope is a per-shape variant cap, so the ADR trail and the header agree on why F5.4b is closed. Note the measured mean of ~12.1 palettes/shape already exceeds ADR-0050's ~7.6 directional reference, which is the substantive argument for closing the item.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
