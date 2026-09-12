# ADR-0177: A pose whose tiles split into two poses the file already carries is labelled a fusion of them, and the composition editor stops offering it as a figure

- Status: accepted (2026-09-12, at the user's request after the measurement
  below; implemented the same day in `Core/NES/HdPacks/SpriteGrouping.cpp`,
  the `poses.json` serializer and `scripts/compose_engine.py`)
- Date: 2026-09-12
- Related: ADR-0170 §1 (the pose sidecar this amends), ADR-0171 (the pose as
  the unit of the sprite layer), ADR-0174 (`sprNNN` sidecars' `poses[]`,
  which cites the entries), ADR-0173 (same shape of defect and the same
  label-don't-delete rule), issue #179
- Supersedes / amends: ADR-0170 §1 — a `poses[]` entry gains an optional
  `fusionOf`; nothing about how a pose is found, identified or counted changes

## Context

`BuildPoses` segments each retained OAM frame into spatially connected
clusters — a DSU over the entries, joined when both axes are within
`kPoseMaxGap` of each other's top-left — and a cluster is a pose. That rule
says *these tiles touched*, and the file reads it as *these tiles are one
figure*. They are not the same statement, and the gap is not rare: any time
one actor walks over, past or into another, the two fuse into a cluster and
the pack gains an entry holding both.

On the Contra golden pack (85 entries), 22 pairs of entries stand in a strict
containment relation — one entry's placement set, normalised to its own
top-left, is wholly inside another's. Rendered, the larger is plainly the
smaller plus a stranger: `pose028` is `pose000` (a running soldier, seen in
1411 frames) with a prone soldier lying beside it. The prone soldier is
`pose014`, an entry of the same file, seen in 140 frames on its own.

An artist scanning the pose list therefore meets the same figure several times
over, each copy carrying a different bystander, with nothing in the file
saying which one is the figure. That is what issue #179 reports, and it is the
mirror image of the defect the 2026-09-12 PRD amendment addressed: there the
unit arrived too small (a figure split across `sprNNN` cells), here it arrives
too large.

**The evidence is structural, and needs no threshold.** If a cluster's tiles
split, at some translation, into exactly two clusters the recorder *also* saw
standing on their own — both already entries of this file, both already past
`kPoseMinFrames` — then the cluster is those two figures touching. Measured
across the whole golden kit, reading the raw sidecars:

| pack | entries | split into two known poses |
|---|---|---|
| Mega Man 3 | 223 | 44 |
| Zelda 1 | 84 | 39 |
| Contra | 85 | 21 |
| Excitebike | 77 | 12 |

and the residue is exactly what it should be. In Contra the four containments
that do *not* split this way are all "a pose plus two loose tiles" — a muzzle
flash, a projectile — shapes below `kPoseMinTiles` that never stand alone and
so are genuinely part of the figure. In Zelda the rule catches
`pose020 = pose019 + pose019`: two copies of one enemy, side by side.

A frequency ratio was measured first and rejected. Across the kit the ratio
between a contained entry's frames and its container's runs continuously from
0.0 to 562 with no plateau, so any cut would be arbitrary; worse, it gets
Excitebike backwards, where the *rarer* silhouette is the contained one
(`pose002`, 541 frames, contains `pose059`, 5 frames).

Non-goals: deciding what a figure *is* (there is no such fact in the OAM
stream — only which tiles touched and which touched alone); splitting a fused
entry into its parts, which are already in the file under their own ids;
re-segmenting the clusters, which would re-cut every pack ever recorded;
anything at run time, where the emulator never reads this file.

## Decision

**The recorder classifies and labels; the consumer filters. Nothing is
deleted.** The same rule ADR-0173 set for `floors[]`, for the same reason.

1. A kept pose `B` is a **fusion** when there exist kept poses `A` and `C`
   and a translation `t` such that `translate(A, t)` is a subset of `B`'s
   tiles and the remainder `B \ translate(A, t)`, re-normalised to its own
   top-left, is exactly `C`'s tile set. `A` and `C` may be the same pose (two
   copies of one shape side by side). Both parts are kept poses by
   construction, so both cleared `kPoseMinFrames` on their own.

   There is no threshold and no constant to tune: the classification is a
   property of the tile sets alone.

2. **The split is chosen deterministically.** Candidates `A` are tried in file
   order — frames descending, then by tile set, which is the order that fixes
   the ids — and the first that yields a known remainder wins. So the named
   first part is the most-seen part the split admits.

3. `PoseEntry` gains `FusionOf`: the two pose indexes, or empty when the entry
   is not classified as a fusion. `Tiles`, `Frames`, `Width` and `Height` are
   written exactly as before, for a fused entry too.

4. The sidecar entry gains one optional field, written only for a fusion, as
   **ids** rather than indexes — the same choice ADR-0174 made, for the same
   reason: ids are what `poses.json` keys an entry by.

   ```json
   { "id": "pose028", "frames": 19, "size": [5, 4],
     "fusionOf": ["pose000", "pose014"],
     "tiles": [ … ] }
   ```

   A sidecar without the field on an entry means *not classified as a
   fusion* — never *proved not to be one*. A pack recorded before this ADR
   has the field nowhere, and reads exactly as it does today.

5. `compose_engine` is the consumer that acts on it. `Pose` gains
   `fusion_of`, and the two places that *choose a figure* act on it:

   - `pose_band_members` excludes a fused pose, so `pose_rank` and the
     suggestion list the composition editor builds from it stop offering an
     entry that is two figures (the filter applies once, since `pose_rank`
     routes through it);
   - `pose_for_anchor` prefers the candidates that are not fused, and falls
     back to the full list only when every pose holding the anchor is
     labelled — a subject the recorder never once saw alone must not be lost
     to the label.

   `Poses.by_id` and `Poses.containing` keep returning them unfiltered: a
   consumer that asks for a specific entry gets it, label and all.

6. `PosesForCells` (ADR-0174's `poses[]` cross-reference on a `sprNNN`
   sidecar) skips fusions. That list exists to say which poses a sheet's cells
   belong to, so that an artist can reach the subject from the sheet; a fused
   entry is not a subject and citing it spends the `kSheetMaxPoseRefs` budget
   on noise.

## Consequences

- On the golden kit, 44 of 223 Mega Man 3 poses, 39 of 84 Zelda 1, 21 of 85
  Contra and 12 of 77 Excitebike are labelled fusions and drop out of the
  editor's suggestion list. Zelda's 46 % is the extreme, and it is the honest
  number: that capture is full of pairs of identical enemies walking into each
  other.
- **Known false-positive class: a single figure whose two halves are also
  drawn separately.** A boss whose head and body appear apart in some other
  frame, a vehicle whose rider dismounts — the whole is labelled a fusion of
  its parts, and the artist has to reach it through the vocabulary sheet or by
  asking for the id. The trade is deliberate: the label costs one suggestion,
  while a fused entry at the head of the list costs the artist the belief that
  a pose is a figure at all. The parts remain individually offerable, which is
  the mitigation the split-cell case never had.
- Nothing about the file's identity, ordering or counts changes, so a pack
  rebuilt with `mep_build.py build` is byte-identical apart from the new
  field, and every existing reader keeps working — the field is optional on
  read in both directions.
- Packs recorded before this ADR keep offering fused poses until re-recorded.
  Nothing breaks; the editor simply does not know yet. Re-recording is a
  bootstrap run.
- The classification is O(poses × poses) in the worst case. It is bounded in
  practice by indexing candidates on their top-left tile's node, so only poses
  that could align at all are tried; `kMaxPoses` (4096) is the ceiling and no
  real pack in the kit exceeds 223.
- A three-figure pile is labelled as a fusion of a figure and a fusion, since
  a part may itself be fused. The chain is left as it is: each link is true,
  and resolving it adds a recursion whose only consumer would be a reader that
  wants the leaves, which nothing does today.
