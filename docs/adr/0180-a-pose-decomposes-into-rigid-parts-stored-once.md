# ADR-0180: A pose decomposes into rigid parts the recorder found recurring across poses, stored once and cited by every pose that wears them

- Status: superseded (2026-09-12, by the user, on the cover measurement) —
  Superseded by: ADR-0179 §4 (`variantOf`), which is the part story the data
  supports. Measured on the golden kit
  (`runs/golden-20260912/spike-pose-parts.md`, summarised at the end of §4):
  the best cover reaches 21–43 % of the poses with 1.0–1.4 parts each, i.e.
  the "part" is the whole figure recurring inside its projectile variant;
  genuine limb parts tile 10 of 37 Contra stage-1 poses and none on Mega
  Man 3, Zelda 1 or Excitebike. A pack format must not carry a block that
  is empty on three of four golden games. The door reopens as a
  *measurement*, not a slice: a game whose `nofig`+`conn` cover (see §4)
  tiles a majority of its kept poses with >= 2 parts each. Slice F9.21 is
  withdrawn from the PRD.
- Date: 2026-09-12
- Related: ADR-0170 (pose sidecar), ADR-0171 (pose as the unit; "a shared
  sub-figure is stored once" is the storage rule this makes visible),
  ADR-0179 (cycles — the rows of the grid this gives columns to), ADR-0153 §2
  (the grouping criterion whose fragments are, in fact, parts), ADR-0174
  (`sprNNN` -> poses cross-reference), ADR-0177 (fusion — a *composition of
  figures*, which this is not), PRD Part A §4 Phase 9 validation test 2,
  `runs/golden-20260912/spike-pose-succession.md` (not versioned)
- Supersedes / amends: ADR-0170 §1 — the file gains optional top-level
  `parts[]` and each entry an optional `composition[]`; `tiles[]` stays and
  stays authoritative

## Context

Contra's player is drawn by the game as two independent sprite groups: a
torso that follows the aim and a pair of legs that follows the run. Every
combination the recording saw is a distinct silhouette, so the sidecar
carries the product — 64 kept poses for perhaps a dozen subjects, most of
the player's entries seen for 3–9 frames. The artist's `BillRizer.png` has
the same product, but as a grid: three torso rows by six leg columns, each
cell a whole figure, and in `hires.txt` the legs referenced once.

Two things follow from the artist's pack that our sheets do not yet do:

1. **The figure is shown whole, the part is stored once.** ADR-0171 already
   decided storage-once for `sprNNN`; what is missing is the *view*: a pose
   shown as "torso T3 at (0,0) + legs L2 at (0,3)" so the artist paints T3
   and L2 and sees eighteen figures change.
2. **A shared part under two different figures needs a condition to be
   painted differently.** Bill and Lance share 136 of 137 tile hashes and the
   same palette on head and torso; the artist spent 98 `spriteNearby`
   conditions anchored on the trousers tile to give Lance his own torso art.
   A recorder that knows which parts compose a pose can emit that condition
   instead of the artist writing it.

The spike measured plausibility only: the largest rigid tile subset shared by
each pair of kept non-fusion poses (same nodes at the same internal offsets,
>= 4 tiles) yields 40 distinct parts on the Contra golden sidecar — the
soldier's 2x2 leg halves (in 31 and 30 pose pairs), the player's 2x4 blue
trousers (18), the 2x5 blue torso-and-trousers (13) — and a naive greedy
cover tiles 24 of 64 poses completely with <= 3 of the top-40 parts. That
says a decomposition exists. It does not pick one: the naive cover leaves 40
poses with a remainder, the "part" that is a whole soldier body (25 pairs) is
a figure that walks into other figures, not a limb, and no measurement yet
says which cover an artist would recognise as torso / legs / arm.

Non-goals: changing what a pose is or how it is counted (`tiles[]` is still
the truth of the entry); naming parts ("torso"); emitting anything into
`hires.txt` in this ADR — §4 lists that as the follow-up it enables; any
change to the `sprNNN` grouping (ADR-0153 §2), whose fragments will often
coincide with parts but are cut by a different rule for a different file.

## Decision

### 1. Parts are found by recurrence across kept poses

At save time, after `BuildPoses` (ADR-0170) and the fusion/variant labels
(ADR-0177/0179), a host-free function in `SpriteGrouping` computes, over the
kept non-fusion poses, the set of **rigid parts**: tile sets with fixed
internal offsets that appear, translated, inside at least `kPartMinPoses` = 2
distinct poses and hold at least `kPoseMinTiles` tiles. Candidate parts are
the maximal common rigid subsets of pose pairs; a part that is another part
plus tiles present in every pose the smaller one appears in is folded into
the larger. Parts are ordered by the number of poses that contain them,
then by tile set, and ids are positions in that order.

### 2. Each pose cites its composition; the remainder stays with the pose

A kept pose gains an optional `composition[]`: the parts that tile it, with
the translation of each, chosen greedily by coverage (largest part first, no
overlap), plus a `rest` count for the tiles no part covers. `tiles[]` is
unchanged and remains the entry's definition; `composition[]` is a view over
it, and a consumer that ignores it reads the pack exactly as before.

```json
"parts": [
  { "id": "part000", "poses": 18, "size": [2, 4],
    "tiles": [ {"node": 3, "dx": 0, "dy": 0}, … ] }
],
"poses": [
  { "id": "pose003", "frames": 644, "size": [3, 6],
    "composition": [ {"part": "part004", "dx": 0, "dy": 0},
                     {"part": "part000", "dx": 1, "dy": 2} ],
    "rest": 0,
    "tiles": [ … ] }
]
```

### 3. The consumer paints parts, and shows figures

The composition editor's sprite picker keeps offering **poses** (ADR-0171 is
untouched) and, when the sidecar has parts, draws a pose's parts as
distinct, labelled regions and lets the artist open the `sprNNN` sheet a
part's tiles live on (ADR-0174 already provides the join). A pose with
`rest > 0` is drawn whole; the rest is simply unlabelled. Together with
ADR-0179 §5 this is the artist's grid: rows from cycles, columns from
phases, cells decomposed into the parts that are actually stored.

### 4. Open points that keep this `proposed`

- **Cover algorithm.** Greedy-by-size is what the spike ran; it is not
  obviously what a human calls torso and legs. Alternatives to measure on
  the golden kit before accepting: prefer parts that occur in more poses
  over larger parts; forbid a part that is itself a kept pose (the walking
  soldier body); require a part to be spatially connected. The acceptance
  measurement is the ADR-0170 shape — poses fully covered with `rest == 0`
  and part count per pose, on all four golden games.
- **Pose-anchored conditions in the exporter.** `mep_build.py` could emit,
  for a tile that belongs to two parts painted differently, the
  `spriteNearby` condition the artist wrote by hand (HD Pack format:
  `<condition>name,spriteNearby,dx,dy,tileData,palette`), anchored on a tile
  of the co-composed part. This is the payoff of §2 and the reason to
  decompose at all; it changes what a rebuilt pack renders, which crosses
  the Phase 9 "nothing inferred breaks rendering" line, so it is a separate
  ADR with its own measurement, not a clause here.
- **Relation to `sprNNN`.** On Contra the ADR-0153 fragments (`spr023` legs
  under two torsos) are exactly the parts; if that holds on the kit, the
  `sprNNN` sheet *is* the part's painting surface and `parts[]` only needs
  to cite it. If it does not hold, parts need a surface of their own, which
  is a bigger decision.

**Measured 2026-09-12** on the F9.22 per-stage packs (kept non-fusion poses;
parts = maximal rigid subsets >= 4 tiles shared by a pose pair, kept when
in >= 2 poses, folded per §1; four greedy covers): the best algorithm
(largest part first) fully covers 16/37 Contra stage-1 poses, 39/147 on the
base, 18/79 Mega Man 3, 5/24 Zelda, 9/36 Excitebike — with 1.0–1.4 parts per
covered pose, i.e. the "part" is mostly the whole figure recurring inside
its projectile variant. Banning parts that are themselves kept poses leaves
10 Contra stage-1 poses tiled by 2.2 parts each (the torso/legs case is
real) and **0** on the three other games. Preferring frequent parts never
beats size; requiring connectivity costs almost nothing and removes the
parts no artist would call a limb. The decomposition this ADR wants exists
on Contra and is marginal elsewhere; ADR-0179 §4's `variantOf` already
carries the rest.

## Consequences

- `poses.json` becomes the single place that says both what a figure looks
  like (`tiles[]`) and what it is made of (`composition[]`); nothing in it is
  authoritative for rendering, so a wrong decomposition costs legibility only.
- Parts are a projection of the same 4096-frame stream as everything else,
  so a part seen under one torso only is not a part. Coverage decides
  decomposition quality as much as the algorithm does; the per-stage
  recording roadmap (PRD F9.22) is a prerequisite for a fair measurement.
- The pairwise step is O(poses² x tiles²) naive; bounded by `kMaxPoses` and
  by indexing candidate translations on shared nodes, as ADR-0177 does.
- Once accepted, ADR-0174's `poses[]` on a `sprNNN` sidecar gains a natural
  companion (`parts[]`), and ADR-0171's storage-once rule stops being
  invisible to the person it was made for.
