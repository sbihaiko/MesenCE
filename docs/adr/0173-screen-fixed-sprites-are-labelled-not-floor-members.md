# ADR-0173: A sprite that never moved is labelled screen-fixed, and the composition editor stops treating it as standing on a floor

- Status: accepted (2026-09-12, implemented the same day in
  `Core/NES/HdPacks/SpriteGrouping.cpp`, the `adjacency.json` serializer and
  `scripts/compose_engine.py`)
- Date: 2026-09-12
- Related: ADR-0164 §1 (the `floors[]` statistic this qualifies), ADR-0165
  and ADR-0171 (the composition editor and the pose ranking that read it),
  ADR-0166, issue #167
- Supersedes / amends: ADR-0164 §1 — `sprites.nodes[]` gains `positions`,
  `frames` and `screenFixed`; `floors[]` itself is unchanged

## Context

`floors[]` answers one question: *who stands on this ground while this shape
is on screen*. It is accumulated from the OAM stream as a histogram of the
sprite's bottom edge (`Y + 8`) quantised to 8 px, and the §5 sprite layer
composes a band out of its members.

A HUD bar is not standing on anything. It is painted at a fixed column, in
several stacked rows, in every single frame — so its bottom edges fall in
several quantised bands at once and it joins every one of them as a member,
with a large count. On Mega Man 3 the weapon-energy segment (sprite node `#0`)
reached **7 distinct bands**, and because it is the most-seen shape in the
whole capture it headed the suggestion list of each of them. An artist
composing an in-world scene was offered a slice of the HUD first.

Measured over a 120 s scripted-play capture (4096 retained OAM frames, 288
sprite nodes), counting each shape's distinct `(X, Y)` screen positions and
the number of frames it appeared in:

| node | appearances | positions | frames | frames/position |
|---|---|---|---|---|
| #16 (HUD) | 1218 | 2 | 1218 | 609.0 |
| #1 (HUD) | 5999 | 7 | 1773 | 253.3 |
| #0 (HUD) | 18809 | 14 | 1955 | 139.6 |
| median of all 288 nodes | — | — | — | **4.3** |

An actor is somewhere new nearly every frame it is on screen. Furniture
returns to the very same pixel over and over. That ratio is a clean signal
and the file did not carry it.

Non-goals: detecting "this is the HUD" semantically (there is no such fact in
the OAM stream — only that a shape did not move); anything at run time, where
the emulator draws no layers from this file; touching the background
statistics, which have their own HUD split already (ADR-0153 §3 routes HUD
cells into `hud.json`/`font.json`).

## Decision

**The recorder classifies and labels; the consumer filters. Nothing is
deleted.**

1. `SpriteAdjacencyStats` gains, per sprite-vocabulary node, `Positions` (how
   many distinct `(X, Y)` the shape was ever drawn at) and `NodeFrames` (how
   many retained frames it appeared in at all — once per frame, however many
   instances). Both are the evidence, and both are written to the file.

2. A node is **screen-fixed** when

   ```
   NodeFrames >= kScreenFixedMinFrames (64)
   and Positions * kScreenFixedRevisits (32) <= NodeFrames
   ```

   — read as "every place this shape was ever drawn, it was drawn again in 32
   different frames on average, and there were enough frames for that to mean
   anything". Below the frame floor nothing is classified: a handful of
   sightings in one spot is not evidence of being pinned there.

3. `adjacency.json`'s `sprites.nodes[]` entries gain three fields, next to the
   existing `floors[]`:

   ```json
   { "cell": 0, "appearances": 18809,
     "floors": [ { "bottom": 72, "count": 3910 }, … ],
     "positions": 14, "frames": 1955, "screenFixed": true,
     "tiles": [ … ] }
   ```

   `floors[]` is written exactly as before, for a screen-fixed node too. The
   label says the bands are where the shape is *painted*; a reader that
   disagrees with the classification has both the verdict and the two numbers
   behind it.

4. `compose_engine.Adjacency` is the consumer that acts on it:
   `band_members(band)` excludes screen-fixed nodes, and `floors()` excludes
   their bands from the band list — so a band only the HUD ever reached stops
   being offered as a band at all. `sprite_rank`, `pose_band_members` and
   `pose_rank` all route through `band_members`, so the filter applies once.

5. A missing `screenFixed` (a pack recorded before this ADR) reads as *not
   classified*, never as false-and-therefore-fine: such a pack's bands are
   exactly what they were, and re-recording is what turns the filter on.

## Consequences

- On the measured Mega Man 3 capture, 30 of 288 sprite nodes are screen-fixed,
  and 19 of the 30 bands shed between 1 and 11 false members apiece (the
  crowded bands hold 60–80 members each). The nodes named in issue #167 are
  all in the set. No band was reached *only* by furniture on this capture, so
  rule 4's band-dropping half did not fire here — it is exercised by the unit
  test, not by this recording.
- **Known false-positive class: an actor that genuinely never moved during the
  capture** — a turret, a boss in its idle loop — is classified as furniture
  and stops being offered for its band. The trade is deliberate: a false
  member poisons a whole band's suggestion list and heads it (furniture is
  always the most-seen shape), while a missing stationary enemy costs one
  suggestion the artist can still reach through the vocabulary sheet. A longer
  capture, or one that walks past the turret twice, dissolves the false
  positive by itself.
- The two thresholds are a judgement call over a measured distribution, not a
  derived quantity — median 4.3 against 139–609 for the HUD leaves a wide
  plateau, and 32 sits in it. They live beside the other adjacency constants
  in `TileSheetTypes.h` and moving them is a recording change, not a format
  change.
- The file grows by three small fields per sprite node.
- Packs recorded before this ADR keep suggesting HUD tiles until re-recorded.
  Nothing breaks; the editor simply does not know yet.
- Not addressed here, and still open: node `#71` of the same capture (130
  appearances, bands 216–240) looks like a genuine spark effect rather than
  this class, and is not distinguished by any rule in this ADR.
