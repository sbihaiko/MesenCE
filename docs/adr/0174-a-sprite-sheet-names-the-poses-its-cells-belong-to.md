# ADR-0174: A `sprNNN` sheet names the poses its cells belong to

- Status: accepted (2026-09-12, at the user's request, with the fix
  implemented in the same turn); reflected in `Core/NES/HdPacks/`
  (`SpriteGrouping`, `SheetRender`, `HdPackBuilder`) and in
  `scripts/core_unit_tests.cpp`
- Date: 2026-09-12
- Related: ADR-0153 (§2 the mutual-predictability criterion that cuts the
  figure, §4 the sheet sidecar schema), ADR-0164 (§1 `sheets/adjacency.json`,
  §5 the sprite layer), ADR-0170 (`sheets/poses.json` — the surface this
  joins to), ADR-0171 (§1 the pose is the unit of the sprite layer, the
  `sprNNN` figure is the fallback), ADR-0172 (the precedent for an optional
  field on a sidecar tile entry), issue #174
- Supersedes / amends: amends ADR-0153 §4 and ADR-0164 §1 — an object/sprite
  sheet sidecar gains an optional `poses[]`. Amends nothing in ADR-0153 §2:
  the grouping criterion, the vocabulary and the sheet layout are untouched.

## Context

The Phase 9 validation panel (section 2, 2026-09-12, an evaluator with no
knowledge of the design) scored the Contra pack against the community pack
`Contra80s` 1.1 and failed 5 of 27 subjects — every failure a human figure,
including the two most-drawn sprites of the capture. A soldier ships cut at
the waist.

The split is measured, not a judgement. In
`runs/golden-20260912/contra/.../auto/textures/sheets/adjacency.json` there
are **35 sprite pairs with `count == coFrames == 1338`** — the legs were
never once on screen without that torso — and 20 of them sit across
`spr023` (legs) and `spr018` (torso). The cause is ADR-0153 §2's denominator:
`spr023`'s legs appear under two different torsos, so each torso edge scores
`count / appearances(legs) ≈ 0.5` and both are dropped, which is exactly what
lets the legs be stored once.

ADR-0171 already decided the **pose** is the unit of the composition editor's
sprite layer, with the `sprNNN` figure as the fallback, so the whole-figure
surface exists: `sheets/poses.json` (ADR-0170) holds one entry per distinct
silhouette. What is missing is any way to get from a sheet to it. The two
surfaces address different things and nothing bridges them:

- `poses.json` addresses tiles by **sprite-vocabulary node**
  (`{"node": 11, "dx": 0, "dy": 0}`);
- no `spr*.json` carries a pose reference of any kind — verified on the
  Contra pack, not one of them contains the substring `pose`.

So an artist who opens `sheets/` sees soldiers cut at the waist and has
nothing telling them a whole-figure surface exists, and section 2 judges the
sheets.

The alternative the issue names first — keep rigidly co-occurring nodes
together on one sheet — is rejected. The criterion decides the vocabulary,
the component partition and the layout of **every** sheet of every pack ever
recorded; loosening it re-cuts all of them, invalidates every `sprNNN` name a
`usrNNN` export or a composition session already cites, and would have to be
measured across the whole 30-ROM library before it could be trusted. A
cross-reference is additive in both directions and costs a pack nothing.

Non-goals:

- Not a change to what a sheet contains, to how cells are grouped, or to
  ADR-0153 §2. Nothing here keys a tile, so nothing here can change what
  reaches the screen.
- Not a change to `poses.json`. The pose sidecar is the source of truth and
  this field points at it; it does not restate a pose's tiles.
- Not a migration. A pack recorded before this ADR carries no `poses[]` and
  must still load.
- Not an answer to "which subject is this" — grouping poses into subjects
  stays where ADR-0170 left it, open.

## Decision

### 1. A group sheet's sidecar carries the pose ids its cells belong to

An object/sprite sheet sidecar gains one optional array of `poseNNN` ids,
written only when it is non-empty:

```json
{
  "kind": "sprite",
  "columns": 2,
  "poses": ["pose001", "pose025", "pose055"],
  "cells": [ ... ]
}
```

An id is the `id` of an entry of `sheets/poses.json`, so the join is a
lookup and not an agreement about array order. A sidecar without the field
is valid and means "a pack recorded before this ADR, or a sheet whose cells
belong to no pose" — readers must not require it, exactly as ADR-0172 §2
made `index` optional.

Only `sprNNN` group sheets get one. `sprites.png` is the entire OAM
vocabulary, so it would cite every pose in the pack and say nothing.

### 2. Order: most of this sheet's nodes covered first

`MesenSheets::PosesForCells` (`Core/NES/HdPacks/SpriteGrouping.{h,cpp}`,
host-free per ADR-0127) returns the position in `poses.json` of every pose
holding at least one of the sheet's cells' vocabulary nodes, ordered by

1. the number of the sheet's **distinct** nodes the pose covers, descending;
2. then the pose's own rank, which is its index — ADR-0170 §1's frames
   descending, then tiles.

So the first entry is the most complete figure this sheet was cut out of.
The list is capped at `kSheetMaxPoseRefs` (32): a node shared by many
silhouettes can be cited by dozens of them, and without a cap the sidecar
would grow with the stream instead of with the sheet. Measured on the
Contra pack, the busiest sheet joins to 23 poses, so the cap does not bite
there; it exists for a 223-pose run like Mega Man 3.

### 3. The poses are segmented once

`HdPackBuilder::WriteSpriteSheets` now runs `BuildPoses` over the sprite
vocabulary it just built, before it names the first `sprNNN`, and
`WritePoseFile` serialises that same table. The per-frame clustering is
O(n²) in an OAM frame's entries over up to `kMaxSheetFrames` frames and must
not run twice.

## Consequences

- A consumer can finally join the two surfaces: open a `sprNNN`, read
  `poses[0]`, look it up in `poses.json` and draw the whole figure. What it
  does with that — render a ghost of the rest of the figure behind the
  sheet, or link to it — is the consumer's decision.
- **The figure is still cut on the sheet.** This ADR makes the split
  navigable, not absent. The panel's section 2 verdict is about what a sheet
  shows, and an artist still paints fragments; the honest claim is that the
  pack no longer *hides* the whole figure.
- Only newly recorded packs carry the field, so any consumer keeps the
  ADR-0171 §1 fallback ladder for a pack without it. That ladder was already
  permanent.
- The sidecar grows by one short array per group sheet — on the Contra pack,
  218 ids across 41 sheets.
- A pack whose OAM stream held no pose (a menu-only recording) writes no
  `poses.json` and therefore no `poses[]` anywhere, which is the same
  "nothing to say" both files already express by absence.
- `mep_build.py`, `mep_lint.py`, `compose_engine` and `sheet_repaint` read
  `cells[]` and are unaffected; like ADR-0172's `index`, the new key must be
  ignored rather than rejected by any reader that validates the schema.
