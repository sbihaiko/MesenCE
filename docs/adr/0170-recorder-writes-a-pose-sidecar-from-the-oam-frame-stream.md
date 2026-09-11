# ADR-0170: The recorder writes a pose sidecar from the OAM frame stream it already holds

- Status: accepted (2026-09-11, by the user) — not yet in the code;
  delivery is scheduled as **Phase 9 debt** (the F9.18 sprite layer composes
  fragments today), not as a Phase 10 prerequisite: PRD Part A §4 Phase 9 /
  §5 order of execution
- Date: 2026-09-09 (accepted 2026-09-11)
- Related: ADR-0153 (§2 the mutual-predictability grouping criterion, §5 the
  retained-stream cap), ADR-0164 (§1 `sheets/adjacency.json`, §5 the sprite
  layer), ADR-0168 (the figure as the composition unit — the walk this
  replaces as the source of pose layout), ADR-0126/ADR-0127 (host-free
  helper + `core_unit_tests` wiring), PRD Part A §4 Phase 9 / Phase 10 spike
  S10.a
- Supersedes / amends: amends ADR-0164 §1 — `sheets/` gains a second sprite
  sidecar next to `adjacency.json`. Does not amend ADR-0168 §1; it removes
  the need for ADR-0168 §2/§3's walk to *guess* a pose.

## Context

Phase 10 assumes a "subject sheet with every pose the recorder saw". PRD
spike S10.a measured whether today's pack can produce one and the answer is
no: the ADR-0168 `evidence[]` walk recovers **1 of 15** Mega Man poses and
**6 of 57** Contra poses as distinct figures, against a >= 80 % criterion,
and in Mega Man 3 **no** `sprNNN` group holds all the tiles of any single
pose. The measured cause is under-grouping, not the cross-pose stacking
ADR-0168 §3 blames: the ADR-0153 §2 criterion (`pAB, pBA >= 0.80` on the
dominant offset) drops every edge from a tile whose offset changes between
poses — the arms, the legs, the gun-arm — so a character's tiles land in
several disjoint always-together fragments. A better walk over that
partition cannot reach a pose, because the partition is not pose-shaped.

The missing datum is co-occurrence *within one frame*. `adjacency.json`
records pairwise totals over the whole retained stream (`pairs[].coFrames`),
which is a projection that cannot be inverted: knowing A and B were often
on screen together does not say whether they were ever in the same
silhouette.

The datum is not missing from the emulator, only from what it writes down.
`HdPackBuilder::RecordOamFrame` already accumulates `_oamFrames` — up to
`MesenSheets::kMaxSheetFrames` distinct frames of at most 128 entries,
consecutive duplicates collapsed into `RepeatCount` — and
`MesenSheets::AccumulateSpriteAdjacency` reads that stream at save time and
throws the per-frame structure away. So ADR-0168 §3's stated reason for
shipping a heuristic ("the exact version cannot be had without re-recording
every pack") is wrong twice: no new capture is needed, and the walk does not
in fact produce clean poses. S10.a's own ground truth was reconstructed
exactly this way, from the live OAM channel of ADR-0169, which is what makes
this sidecar's sufficiency a measured claim rather than a hope.

Non-goals:

- Not a change to capture. No PPU hook, no new recording pass, no change to
  `_oamFrames`, to `kMaxSheetFrames` or to the `RepeatCount` collapse.
- Not a migration. Packs recorded before this ADR have no pose sidecar and
  keep composing exactly as they do today (ADR-0153/ADR-0160 position).
- Not a change to the `sprNNN` vocabulary or to `hires.txt`. Nothing here
  keys a tile, so nothing here can break rendering (the Phase 9 rule).
- Not an animation format. A pose is a still silhouette with a frame count;
  ordering poses into an animation, naming them ("run", "jump") and
  identifying the same character across poses are separate questions.
- Not a decision about Phase 10. Whether a subject is the unit of a restyle
  stays open (ADR-0168 §1 covers the editor's unit only).

## Decision

### 1. `sheets/poses.json` — one entry per distinct silhouette

At save time, alongside `adjacency.json`, the recorder writes
`textures/sheets/poses.json`. For every retained OAM frame it segments the
frame's entries into **spatially connected clusters** (two entries are
connected when their 8x8 boxes are within 8 px on both axes), normalises
each cluster to its own top-left, and expresses it as a set of
`(node, dx, dy)` in 8 px tile units, using the existing
`SpriteGrouping::ToCells` round-to-nearest-cell rule. `node` is an index
into the sprite vocabulary — the same index space as `adjacency.json`
`sprites.nodes[]`.

Two clusters are the **same pose** when that set is equal. Identical sets
merge, summing the frames they were seen in (a frame counts `RepeatCount`
times, as elsewhere in the stream).

```json
{
  "unit": 8,
  "frames": 1440,
  "poses": [
    {
      "id": "pose000",
      "frames": 412,
      "size": [3, 4],
      "tiles": [
        {"node": 12, "dx": 0, "dy": 0},
        {"node": 47, "dx": 1, "dy": 0}
      ]
    }
  ]
}
```

`poses[]` is sorted by `frames` descending, then by `id`, so the file is
deterministic for a given stream. `size` is the cluster's extent in cells,
for a consumer that lays poses out without walking `tiles[]`.

### 2. Retention: >= 3 frames and >= 4 tiles, capped at 4096 poses

A pose is kept when it was seen in at least 3 retained frames and holds at
least 4 tiles. Both thresholds are the ones S10.a measured with; they exist
to keep transient garbage (a one-frame explosion mid-redraw, a lone
projectile) out of a file an artist reads. The kept set is capped at 4096
entries by `frames` descending, mirroring `kMaxSheetFrames`, so the file
cannot grow without bound on a long session. The counts a consumer needs to
judge truncation — total retained frames, poses before and after the
threshold and the cap — go in the save-time report line, next to the
existing "N sprite nodes from M OAM frames".

**Made exact while implementing (2026-09-11).** The prose above leaves three
readings open, and the implementation and its tests pin these:

- The frame floor is counted the way §1 counts frames — `RepeatCount`
  included. A silhouette held through one frame repeated five times clears
  it. That is deliberate: a pose is a still, so a static screen showing one
  really is evidence the pose exists, and unlike the pair statistics
  (`SelectSpriteEdges`, which ignores `RepeatCount` on purpose) a paused
  screen cannot manufacture a *second* pose.
- The tile floor runs inside the frame loop, so a cluster under 4 tiles
  never enters the table: the reported "found" count is already past the
  tile floor, and only the frame floor separates "found" from "kept".
- "Kept" is counted before the cap. `PosesKept > poses[]` is the legitimate
  state that says the session outgrew the file, which is what the report
  line exists to show.

### 3. The segmentation lives in `SpriteGrouping`, host-free and unit-tested

The clustering, normalisation, dedup and thresholds are a free function in
`Core/NES/HdPacks/SpriteGrouping.{h,cpp}` (`BuildPoses`), taking the OAM
frame stream and the sprite vocabulary and returning the entries — no
`HdPackBuilder` state, no I/O, per ADR-0127. `HdPackBuilder` only serialises
what it returns. It is covered by `core_unit_tests` (ADR-0126) with
hand-built frame streams: two poses of one character that share a torso tile
stay two poses; an 8 px diagonal gap connects and a 9 px gap does not; a
`RepeatCount` frame counts its repeats; the thresholds and the cap drop what
they claim to drop.

### 4. Pose layout supersedes the walk where both apply

A consumer that has `poses.json` takes a figure's layout from it and does
**not** run the ADR-0168 §2 `evidence[]` walk: the walk's occupied-slot
heuristic (§3) exists only to guess what this file states. The walk stays as
the fallback for a pack without the sidecar. ADR-0168 §1 is untouched — the
unit of the sprite layer is still a figure, and a pose is a better figure
than a fragment.

## Consequences

- Only newly recorded packs get poses, so the composition editor carries
  two layout paths (sidecar, walk) until the old packs are re-recorded. The
  fallback is not dead code to delete later; a pack recorded today is a
  legitimate input forever.
- `poses.json` is a second file that can disagree with `adjacency.json` —
  same stream, different projection. They are written in the same pass from
  the same `_oamFrames`, which is the only guarantee offered; nothing
  cross-checks them, and a consumer that mixes a pose's `tiles[]` with a
  pair's `offsets[]` is on its own.
- Sets-equal identity is strict: the same body pose with the projectile one
  cell further away is a different pose. S10.a saw this inflate a
  denominator (15 Mega Man poses where a human would count 10-12). A looser
  identity (ignore members below a frequency, or cluster by Jaccard) is a
  decision this ADR declines to take without a measurement, because
  loosening it can merge two real poses and that failure is invisible in the
  file.
- Contact between actors merges them: in Contra, an enemy touching Bill is
  one cluster, so a "pose" can be two characters. Connectivity is the only
  signal the OAM stream carries; separating actors needs identity, which the
  pack does not have.
- A Phase 10 subject sheet becomes buildable from a pack, but this ADR does
  not build one: grouping poses *of the same subject* is still open, and
  S10.b's layout-fidelity question is untouched.
- The sidecar exposes screen positions only as relative offsets, so it adds
  no new ROM-derived information beyond what `sprites.png` already shows.
