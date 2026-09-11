# ADR-0171: The sprite layer composes poses; the `sprNNN` figure is the fallback unit

- Status: accepted (2026-09-11, by the user) — not yet in the editor; the
  implementing slice is PRD Part A §4 Phase 9 (F9.18's sprite layer)
- Date: 2026-09-11
- Related: ADR-0164 (§5 the sprite layer and its Y-band criterion, §3 the
  `usrNNN` export contract), ADR-0165 (the editor is an external stdlib
  Python tool over a host-free engine), ADR-0170 (`sheets/poses.json`, and
  §4 the rule that a consumer with the sidecar does not run the walk),
  ADR-0153 (§2 the grouping criterion that produces `sprNNN`), ADR-0161
  (palette variants are positional), PRD Part A §4 Phase 9 / spike S10.a
- Supersedes / amends: supersedes ADR-0168 — keeps its §1 principle (a node
  is not a unit an artist can judge), replaces its answer (the `sprNNN`
  figure) with the pose, and demotes its §2/§3 walk to the fallback path
  ADR-0170 §4 already defines. Amends ADR-0164 §5: the unit of every
  gesture in the sprite layer is the pose, and band membership is read off
  the pose's bottom row rather than off a single shape.

## Context

ADR-0168 decided that the sprite layer composes figures rather than OAM
nodes, because a node is one 8x8 fragment and a row of nodes comes out
striped. That reasoning was right and the first human pass confirmed it.
Its *answer* — the figure is a `sprNNN` group, reassembled by walking the
group sheet's `evidence[]` offsets — was the best the data allowed in
September 2026, and spike S10.a measured it against a denominator two days
later: the walk recovers **6.7 %** (Mega Man 3) and **10.5 %** (Contra) of a
character's poses. The binding cause is under-grouping, not the cross-pose
stacking ADR-0168 §3 blames: a `sprNNN` group is a *sub-part* of a pose,
mean 5.1 tiles against a mean pose of 10.8, because ADR-0153 §2's 0.80
mutual-predictability test drops every edge from a tile that changes offset
between poses — the arms, the legs, the gun-arm.

So accepting ADR-0168 as written would buy the editor a unit of about five
tiles: better than a node, still a fragment, and still the verdict the
Phase 9 human panel would report.

ADR-0170 changed the available data. The recorder now writes
`textures/sheets/poses.json` — one entry per distinct silhouette, from the
per-frame structure the pairwise statistics discard — and S10.a re-measured
on 2026-09-11 puts **25 of 25** of a character's poses in the file, 68 of 72
of every pose the run drew. The complete silhouette is now a thing the pack
states, so the unit ADR-0168 wanted is available and the one it settled for
is not the best on offer.

This ADR therefore keeps ADR-0168's principle and replaces its answer. It is
a supersede rather than an amendment because ADR-0168's own title asserts
that "the group sheet's `evidence[]` offsets reassemble the character",
which the measurement falsified.

Non-goals:

- Not a change to the recorder or to any sidecar format. Every byte this
  needs is written by ADR-0170 and ADR-0164.
- Not a grouping of poses into subjects. ADR-0170 declines that, and this
  ADR does not reopen it: a pose is addressed through its anchor node, the
  same identity ADR-0168 §4 already persists in `seed`/`locked`.
- Not a change to how a band is *defined* (ADR-0164 §5's bottom-edge
  quantisation), nor a fix for the known defect that screen-fixed HUD tiles
  pollute `floors[]` bands.
- Not a migration. A pack recorded before ADR-0170 has no sidecar and keeps
  composing exactly as it does today.
- Not a runtime concept. The emulator draws no poses; ADR-0164 §3's export
  contract is unchanged.

## Decision

### 1. The unit of the sprite layer is the pose

A **pose** is one entry of `sheets/poses.json`: a set of `(node, dx, dy)` in
8 px cells, normalised to its own top-left, with the frame count it was seen
in. In the sprite layer a pose is what the editor seeds on, ranks, locks,
swaps, previews and draws.

The fallback ladder, in order, is:

1. the pose containing the gesture's anchor node, from `poses.json`;
2. failing that — no sidecar, or an anchor in no pose — the `sprNNN` figure
   laid out by the ADR-0168 §2 walk, which survives for exactly this;
3. failing that, the bare node, as a degenerate pose of one. A lone
   projectile that never grouped already is one.

The background and object layers are untouched: a background node is a
16x16 metatile, self-contained art, and composing those node-by-node is
already legible.

### 2. Layout comes from the pose, never from a walk when a pose exists

ADR-0170 §4 already states this rule and `compose_engine.Pack`
(`figure_layout_detail`) already implements the boundary, reporting which
source it used. Nothing here changes it. A pose's cells are drawn at its own
`dx`/`dy`; its bounding box is `size`.

A pose may hold nodes the anchor's `sprNNN` sheet does not list — that is
the measured point of this ADR, not a defect. The editor draws the pose.

### 3. A pose's band is its bottom row

ADR-0164 §5 puts a candidate in a Y band by its bottom edge. A pose has
several. Its band membership is the set of bands of its **bottom-row nodes**
— the members at `max(dy)` — so a pose belongs to a band when the part of it
that stands on the floor does. This keeps the ADR-0164 §5 acceptance
("the sprite band containing Ryu's bottom edge ranks ground enemies above
projectiles") meaningful at pose granularity: a projectile crossing at head
height does not join a ground band merely because its owner's feet do.

### 4. Ranking: summed co-presence, damped by size

`sprite_rank` scores nodes by `coFrames` summed against the locked set. A
pose has many members, and ADR-0168 left the denominator open. It is fixed
here:

```
score(pose) = ( sum over distinct member nodes of coFrames(node, locked) )
              / sqrt(number of distinct member nodes)
```

sorted by `score` descending, then by the pose's `frames` descending, then
by `id`. A pose with no co-presence at all against the locked set is not a
candidate, exactly as a node with `co == 0` is not one today.

The rationale is the one the alternatives fail: a bare sum lets an 11-tile
pose outrank a 4-tile one on size alone, and a mean inverts the bias into a
preference for small poses, which are the fragments this ADR exists to stop
promoting. The square root damps the size term without reversing it. This is
a ranking heuristic over recorded evidence, not a derived quantity, and the
implementing code says so.

### 5. Export is unchanged

A composed sprite band still exports as a `usrNNN` sidecar of kind `sprite`
per ADR-0164 §3 — `cells[]` at composed positions, `"composed": true`,
`seed`/`locked`/`band`. Composing poses changes which cells land where, not
the file. `mep_build.py` needs no change, and `seed`/`locked` keep naming
**nodes**: a pose is resolved from its anchor on reopen. No new field.

## Consequences

- The editor's grid, suggestion list and preview take variable-sized cells
  (a pose is roughly 16x16 to 48x48, not a uniform 8x8), so the View's
  fixed-cell geometry and hit-testing are rewritten rather than adjusted.
  This cost is unchanged from ADR-0168 — it is the price of any unit larger
  than a node — and the MVVM split of ADR-0165 plus the host-free
  `compose_editor_layout.py` (where `cell_origin`/`index_at` are exact
  inverses) is what keeps it affordable.
- **A pose can be two characters.** ADR-0170's connectivity is the only
  signal the OAM stream carries, so an enemy touching Bill Rizer is one
  cluster. This is accepted, not mitigated: the `frames`-descending order
  puts the solo pose above the contact pose in the candidate list, and a
  two-character silhouette is still a coherent picture of what the screen
  showed — unlike a loose arm. Separating actors needs identity the pack
  does not have.
- Strict set identity inflates the candidate list: the same body with a
  projectile one cell away is a different pose (223 poses on a 300 s Mega
  Man 3 run, 25 of them the main character's). The `budget` argument of
  `sprite_rank` already caps what reaches the artist; loosening pose
  identity is ADR-0170's decision to revisit, not this one's.
- Two layout paths live in the engine indefinitely — pose and walk — because
  a pack recorded before ADR-0170 is a legitimate input forever. The walk is
  not dead code, and ADR-0168 stays readable in the register for that
  reason.
- The Phase 9 human panel should run only against a pack recorded since
  ADR-0170. Judging the sprite layer on an older pack measures the fallback,
  which is the thing already known to score 6.7 %.
