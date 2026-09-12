# ADR-0176: Sprite grouping counts both sides of its ratio per frame, so a shape drawn twice in one frame can still join a group

- Status: accepted (2026-09-12, at the user's request after the measurement
  below; implemented the same day in `Core/NES/HdPacks/SpriteGrouping.cpp`)
- Date: 2026-09-12
- Related: ADR-0153 §2 (the mutual-predictability criterion this corrects on
  the sprite side), ADR-0164 §1, ADR-0173 (the same biased denominator, fixed
  for `floors[]`), ADR-0174 (the pose join that makes a split recoverable but
  not unnecessary), issue #176
- Supersedes / amends: ADR-0153 §2, for the OAM analogue only — the background
  criterion is unchanged and was never affected

## Context

`SelectSpriteEdges` keeps a pair only when each shape predicts the other:

```cpp
double probAb = (double)count / appearA;
double probBa = (double)count / appearB;
if(probAb < minProb || probBa < minProb) { continue; }   // kSheetMinPairProb = 0.80
```

`count` is how often the pair was seen at its dominant relative offset.
`appearA` comes from `Appearances[cell]++`, which `Accumulate` increments once
per **OAM entry**. The two are not on the same basis: a shape drawn twice in a
frame scores two appearances, while the dominant offset can only be hit by one
of those two instances when the repeats sit in different contexts.

The arithmetic ceiling is then `1 / (appearances per frame)`. At two
appearances per frame the best possible probability is 0.5, against a
threshold of 0.80, so **every edge from that shape is dropped** — however
rigidly it sits beside its neighbour. The evidence is never consulted; the
denominator decides.

The visible symptom, and how this was found: `spr016.orig.png` on the Contra
pack renders `GA M` / `OV R`. The missing `E` is not a de-duplicated repeat
placed in one slot — it is in **zero** slots. The glyph occurs twice per frame
("GAME" and "OVER"), which is exactly this case.

Measured over the whole golden kit (`runs/golden-20260912/`, not versioned),
from `appearances / frames`, both fields already in `adjacency.json` since
ADR-0173:

| pack | sprite nodes | repeat within a frame (> 1.01) | ungroupable by arithmetic (> 1.25) |
|---|---|---|---|
| Mega Man 3 | 288 | 73 (25 %) | **42 (15 %)** |
| Zelda 1 | 123 | — | **18 (15 %)** |
| Contra | 248 | 30 (12 %) | **16 (6 %)** |
| Excitebike | 208 | — | **9 (4 %)** |

The median node sits at exactly 1.00, so this is not a broad distortion of the
statistic — it is a clean minority that is silently excluded. Mega Man 3 has
three nodes at a ratio near 31, which no threshold in (0, 1] could admit.

This is the same error ADR-0173 found in `floors[]`: a per-frame numerator
over an instance-counted denominator. That ADR added `NodeFrames` for exactly
this reason; the grouping criterion never got the same treatment.

Non-goals: changing `kSheetMinPairCount` or `kSheetMinPairProb` (the threshold
is not what is wrong); the background criterion in
`SheetGrouping::SelectDirection`, where numerator and denominator are both
per-placement and therefore already consistent; making a pack recorded before
this ADR group differently, which only a re-record can do.

## Decision

**Both sides of the ratio are counted once per frame.**

1. `SpriteStats` counts, per vocabulary cell, the number of **frames** the
   shape appeared in at all (once per frame, however many instances) — the
   same quantity ADR-0173 named `NodeFrames`, computed here from the same
   de-duplicated frame stream.

2. For an ordered pair and a relative offset, the tally is incremented **at
   most once per frame**: the frame counts when *some* instance of A has
   *some* instance of B at that offset. A second instance pair at the same
   offset in the same frame does not raise it.

3. The criterion is then read as: *of the frames in which A appears, in how
   many is there an A with a B at this offset*. Both `probAb` and `probBa`
   use the per-frame numerator over the per-frame denominator, and
   `kSheetMinPairCount` / `kSheetMinPairProb` keep their current **values**.

   `kSheetMinPairProb` also keeps its meaning. `kSheetMinPairCount` does not:
   the floor it applies to is now a count of frames, where it used to be a
   count of instance pairs. Amended 2026-09-12, after measurement — see the
   Consequences.

4. `Appearances` stays in the file and in `adjacency.json` unchanged — it is
   the honest instance count and ADR-0173's `positions`/`frames` pair reads
   against it. Only the grouping ratio stops using it.

## Consequences

- A shape that repeats within a frame becomes groupable on the evidence rather
  than being excluded by arithmetic. On the measured kit that is 4–15 % of
  sprite nodes per pack.
- **A deliberate loosening.** Under the old reading, a shape appearing twice
  with only one instance beside B scored 0.5, "half of A's appearances predict
  B". Under the new one it scores 1.0, "whenever A is on screen, an A is
  beside B". The second is the statement grouping actually needs — a sheet
  cell is a shape, not an instance — but it does admit pairs the old rule
  refused for a reason that was not purely the denominator bug. The
  `kSheetMinPairCount` floor of 3 frames is what still guards against
  coincidence.
- **Sheet layout changes for newly recorded packs.** Existing packs keep
  loading and are untouched; they simply do not benefit until re-recorded.
  This is the cost ADR-0174 declined to pay for the split-figure problem, and
  it is paid here because there is no additive alternative: an edge that was
  never created cannot be cross-referenced later.
- **`kSheetMinPairCount` becomes a floor on frames, and that removes some
  groups.** Measured on Excitebike: nodes 183 and 184 formed the two-cell
  group `spr033` on the strength of 8 instance pairs — but those 8 came from
  **2 frames**, in which the shape was drawn 4 times each. The old rule saw
  `count = 8 >= 3` and `prob = 8/8 = 1.0`; the new one sees `count = 2 < 3`
  and drops the edge. This is the floor finally meaning what it says, and it
  is the same concern `Accumulate`'s own comment already names about
  `RepeatCount` — a handful of frames must not be able to manufacture the
  minimum count. Two frames is not evidence of a group. The effect is small
  and one-directional where the evidence is real: across the golden kit,
  Mega Man 3 gains 18 placements and loses none, Zelda 1 gains 5 and loses
  none, Contra gains 1 and loses none, and Excitebike loses exactly this pair
  and gains none.
- ADR-0174's `poses[]` join is unaffected and still needed — poses come from
  the silhouette stream, not from these edges.
- The `E` of `spr016` is the acceptance case, and a pack re-recorded after
  this ADR should show it in a slot.
