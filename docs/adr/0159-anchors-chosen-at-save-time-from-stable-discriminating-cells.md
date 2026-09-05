# ADR-0159: A captured screen's anchors are chosen at save time, from cells its variants do not change and its rivals do not share

- Status: accepted — reflected in `Core/NES/HdPacks/{ScreenStitcher,HdPackBuilder,TileSheetTypes}`; the code landed with the measurement, this ADR records the decision behind it
- Date: 2026-09-05
- Related: ADR-0050 (bootstrap `<background>` capture), ADR-0153 (sheets), ADR-0156 (screen residency), PRD Part A Phase 9, issue #164, `Core/NES/HdPacks/ScreenStitcher.cpp`, `Core/NES/HdPacks/HdPackBuilder.cpp`, `scripts/spike_anchor_stability.py`
- Amends: ADR-0050 §Decision, the clause "up to three `tileAtPosition` anchors (rarest non-flat tiles on screen, ≥ 64 px apart)" — both the criterion and the moment it is applied. Lifts ADR-0156 §Non-goals' exclusion of "changing what `CaptureScreen` captures, or its anchors".

## Context

ADR-0050 gates every captured screen on up to three `tileAtPosition`
conditions, picked as the rarest non-flat tiles on the frame, at least 64 px
apart, **at the moment the screen is captured**. ADR-0156 then made those
conditions load-bearing in a second way: a routed scene cell leaves
`metatiles.png` because the `<background>` is expected to paint it. When the
condition set does not match, the cell is drawn vanilla and the routing has
removed art nothing replaces.

Two properties are needed and neither was measured. An anchor must be
**stable** — a cell no later variant of the same screen changes, or the
`<background>` stops drawing on the next score digit — and it must
**discriminate** — a set no unrelated screen satisfies, or the wrong screen is
drawn whole.

`scripts/spike_anchor_stability.py` measured the shipped rule over the 30-pack
library (1166 screens, 3487 anchors; two screens count as variants when they
agree on ≥ 90 % of their 960 8x8 blocks):

- 1558 of 3487 anchors (44.7 %) sit on a cell a variant of their own screen
  changes; 866 of 1166 screens (74.3 %) carry at least one;
- 21424 of 29218 variant pairs (73.3 %) therefore do not draw;
- 3563 of 80902 unrelated pairs (4.4 %) match falsely.

Donkey Kong 128/162 anchors unstable, Tetris 2 277/357, F-1 Race 203/279,
Golf 100/306 with 6080/10100 variant pairs missed.

**The fix the issue proposed does not work, and the same measurement says so.**
Preferring cells no variant changes, as a straight filter over the rarity
ranking, collapses the misses to 36/29218 (0.1 %) and explodes false matches
to 16237/80902 (**20.1 %**) — Bomberman 861 → 8274, Tetris 2 642 → 7857. The
reason is structural: what survives every variant is the frame border every
other screen also has. Rarity was buying discrimination, and a false match
draws the wrong screen whole, which is worse than a gap in one.

**Non-goals.** This does not change what is captured, when a screen is
captured, the `screenNNN` numbering, priority 20, the 300-screen cap, or
ADR-0156's residency rule. It does not touch `hud`/`font`/`misc`. It does not
address palette-swapped variants (see Consequences).

## Decision

**1. Stability is the filter; discrimination is the objective.** Among the
candidate cells that no variant of this screen changes, the pick greedily
takes the ones leaving the fewest rival frames still matching. When the stable
region cannot fill three conditions, or cannot separate the screen from its
rivals, the pool widens to the volatile cells rather than ship an ambiguous
set — an anchor that sometimes fails to draw beats one that draws the wrong
screen. ADR-0050's three-condition cap and 64 px spread are kept.

**2. The pick happens at save time, not at capture time.** This is the
load-bearing half. A screen is captured the first time it holds still, so at
that moment every later variant of it — the next score digit, the other half
of a blink — is still in the future. The evidence only exists once the session
is over. `HdPackBuilder::CaptureScreen` now records a `PendingScreen` with up
to 160 rarity-ranked, tile-aligned candidates and pushes the bitmap (so
numbering and ADR-0156's `GridFrame::Captured` tie are unchanged);
`FinalizeScreenAnchors()` runs immediately before `BuildSheets()`, so the
`<condition>` and `<background>` lines serialize in the same order and
position as before.

**3. The rule is host-free and testable.** `MesenSheets::SelectScreenAnchors(
frames, capturedIndex, candidates)` returns `AnchorChoice{Picked, Rivals,
UsedVolatileCell}`. A frame is a variant or a rival of the captured frame only
under the **same `FineX`** — a frame at another fine scroll is not the pixel a
`tileAtPosition` reads. A `capturedIndex` out of range (past `kMaxSheetFrames`,
or no retained frame) degrades to ADR-0050's plain rarity-and-spread greedy,
never to no anchors at all.

**4. Constants**, in `TileSheetTypes.h` with the measurement in the comment:
`kAnchorVariantAgree` 0.90, `kAnchorCandidateCap` 40, `kAnchorCount` 3,
`kAnchorMinSpread` 64. Sensitivity: at 0.85 the miss rate goes 77.1 % → 30.4 %,
at 0.95 72.1 % → 9.5 %; false matches drop ~5x at every setting.

Projected on the same library: variant pairs missed 73.3 % → **13.4 %**, false
matches 4.4 % → **0.88 %**. Both move the right way, which is what rules out
the stability-only rule.

## Consequences

The projection is a projection, and its model differs from the shipped rule in
three ways that all matter: the spike compares pixels of *captured* screens
while the implementation compares palette-agnostic shape ids across the whole
retained grid stream (more evidence, so 13.4 % is likely pessimistic); the
spike's rivals are the other captured screens while the implementation's are
every retained frame at the same `FineX` (so 0.88 % is measured on a smaller
universe); and the condition compares tile index + palette while the spike
compares pixels (so the 73.3 % shipped miss rate is a lower bound). The
figures are direction, not a guarantee.

**Palette-swapped variants stay unfixed.** `ShapeId` is `GetKey(true)`, palette
wildcarded, so a variant that only recolours the anchor tile reads as stable in
the grid while the condition — which compares `PaletteColors` — fails. One of
the three failure modes issue #164 names is therefore untouched. Fixing it
needs palette in the retained stream, which is an ADR-sized change to
`GridFrame` and is deliberately not made here.

Candidates are now restricted to tile-aligned runs, so a screen whose every
non-flat tile is off-grid would yield no candidates, no `<background>` and no
`Captured` flag. Save-time cost is bounded by 300 screens x `kMaxSheetFrames`
of variant classification, cut down by an early exit on the mismatch budget;
it is not profiled on a real save. Screens captured before a mid-session
`SaveHdPack` are anchored against a shorter stream than screens captured after
it.
