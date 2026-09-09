# ADR-0168: The sprite layer composes `sprNNN` figures, not OAM nodes — the group sheet's `evidence[]` offsets reassemble the character

- Status: proposed (evidence amended 2026-09-09 — see "Measured" below)
- Date: 2026-09-07
- Related: ADR-0164 (§1 `sprNNN.json` `evidence[]`, §5 the sprite layer and
  its Y-band criterion), ADR-0165 (the editor is an external stdlib Python
  tool over a host-free engine), ADR-0153 (§2 the grouping criterion that
  produces `sprNNN`, §3 the `sprites.png` vocabulary sheet), ADR-0161
  (palette variants are positional)
- Supersedes / amends: amends ADR-0164 §5 — the figure becomes the unit of
  *every* gesture in the sprite layer (seed, rank, lock, swap, preview,
  export), not only of the placement step, and its layout is read from
  `sprNNN.json` `evidence[]` rather than from `adjacency.json`
  `pairs[].offsets[]`.

## Context

ADR-0164 §5 defined the sprite layer as a Y band of OAM shapes, and
ADR-0165 shipped an editor over it. The editor composes at **node**
granularity: the gradeado's cells, the ranked suggestion list and the
selection preview are all individual `sprites.json` nodes.

A node is one 8×8 OAM entry. It is a fragment of a character and almost
never a character. So a row of sprite nodes is a row of unrelated 8-pixel
slivers, and the first human pass over the editor (F9.18, the Phase 9 panel)
reported exactly that: everything comes out striped. That verdict is
correct, and it is not a rendering bug — `Pack.node_art` and
`Sheet.cell_image` were checked against hand-decoded 2bpp CHR bytes and are
right to the pixel. The tool is drawing the wrong unit.

`spike_compose_scene.py` was written to test the alternative against
recorded data, on two independent packs:

- **Mega Man 3.** `spr000` is 13 nodes; walking its `evidence[]` offsets out
  from an anchor placed all 13 with none left over, and the result is
  recognisably Mega Man. Five more groups reassembled the same way.
- **The Legend of Zelda.** A separate recording, a different mapper, a
  different vocabulary: the node row is fragments of the HUD (half a heart,
  a rupee, a digit); the reassembled groups are whole overworld bushes.

The data needed was already on disk and already specified. ADR-0164 §1 makes
`sprNNN.json` carry one `evidence[]` entry per surviving ordered tile pair
with the `dx`/`dy` between them — 78 entries for `spr000`'s 13 nodes,
all-pairs. ADR-0164 §5 even names the figure ("the near-field `offsets[]`
histogram then places a candidate's *figure* (its `sprNNN` group)"), but it
treats the figure as something the *placement* step resolves at the end,
while everything upstream still ranks and locks nodes. The spike shows the
figure has to be the unit from the first gesture, because a node is not
something an artist can look at and judge.

One thing the spike did **not** solve, and this ADR does not claim to: a
`sprNNN` group spans several animation frames of the same character, so the
all-pairs offsets describe more than one pose. Walking them naively stacks
two poses on top of each other. The spike's mitigation is a heuristic — take
edges most-observed first and refuse a slot already taken — which produces
one clean pose on the six groups tried, but is not derived from anything the
pack records. The pack does not record which tiles co-occurred in the same
OAM frame, only pairwise totals over the retained stream.

### Measured, 2026-09-09 (PRD Phase 10 spike S10.a)

The spike above was a demonstration on six hand-picked groups. S10.a counted
the same walk against a denominator, on two fresh 300 s recordings (Mega Man
3, MMC3/CHR-ROM; Contra, CHR-RAM), with the poses actually drawn read off
ADR-0169's live OAM channel — a pose being one spatially connected OAM
cluster normalised to its own top-left, using `SpriteGrouping::ToCells`'
round-to-nearest-cell rule, kept when seen in >= 3 captures with >= 4 tiles.
Decode validity: 98.7 % (MM3) / 94.4 % (Contra) of the decoded OAM tiles are
present in the pack's own `sprites.json` vocabulary.

| | Mega Man 3 | Contra |
|---|---|---|
| poses drawn (denominator) | 15 | 57 |
| recovered as a distinct figure (Jaccard >= 0.8) | 1 (6.7 %) | 6 (10.5 %) |
| poses whose tiles all fit in one `sprNNN` | 0 / 15 | 3 / 57 |
| mean group size vs. mean pose size (tiles) | 5.1 vs 10.8 | 4.7 vs 10.4 |

Against the S10.a criterion (>= 80 % of a main character's poses, HUD
excluded) this is a **fail**, and no reading of the numbers gets within 4x:
at a generous Jaccard >= 0.6 it is 13 % / 23 %, and restricting Contra to
poses of >= 8 tiles makes it worse (4 %).

**The mechanism is not the one §3 names.** §3 blames cross-pose stacking and
defends the occupied-slot guard, but that guard almost never fires: 11/12
(MM3) and 33/33 (Contra) of the character's groups place every member. The
binding failure is **under-grouping** — a `sprNNN` group is a *sub-part* of a
pose. The ADR-0153 §2 mutual-predictability test at `pAB, pBA >= 0.80` on the
dominant offset drops every edge from a tile that changes offset between
poses, i.e. exactly the arms, legs and gun-arm that distinguish one pose from
another, so a character's tiles fall into several disjoint always-together
fragments. The partition the walk walks was never pose-shaped, so no
refinement of the walk reaches a pose. §1 (the figure, not the node, is the
unit) is unaffected and still holds: a node row is unreadable, and the
fragments are at least recognisable art.

Evidence: `runs/s10a-shared/S10a-summary.json` and
`runs/s10a-{mm3,contra}/analysis/` (gitignored, not versioned).

Non-goals:

- Not a change to the recorder or to any sidecar format. Every byte this
  needs is already written by `SpriteGrouping::SelectSpriteEdges`.
- Not a change to the Y-band criterion of ADR-0164 §5. Which shapes share a
  floor is a separate question, with a separate known defect (screen-fixed
  HUD tiles land in `floors[]` bands by Y coincidence) that this ADR does
  not address.
- Not the "true scene position" layout. Placing figures at their real
  relative positions on screen remains out of reach and out of scope.
- Not a runtime concept. The emulator still draws no figures; the export
  contract of ADR-0164 §3 is unchanged.

## Decision

### 1. The unit of the sprite layer is the figure

A **figure** is a `sprNNN` group: its member nodes plus a position in 8 px
tile units for each. In the sprite layer, a figure is what the editor seeds
on, ranks, locks, swaps, previews and draws. A bare node is addressable only
as a degenerate figure — a group of one, which is what a lone projectile
that never grouped already is.

The background/object layers are untouched: a background node is a 16×16
metatile, a self-contained piece of art, and composing those node-by-node is
already legible.

### 2. Layout comes from `sprNNN.json` `evidence[]`, most-observed first

Given a group sheet, positions are resolved by:

1. anchoring the sheet's first `cells[]` entry at `(0, 0)`;
2. walking `evidence[]` sorted by `count` descending, repeatedly: for an
   edge `(a, b, dx, dy)` with exactly one endpoint placed, the other is
   placed at that endpoint ± `(dx, dy)`;
3. **refusing a slot already occupied** — the cross-pose guard. A tile whose
   only remaining edges all point at taken slots stays unplaced;
4. repeating until no edge places anything new.

`dx`/`dy` are in tile units in the group sidecar (unlike `adjacency.json`
`pairs[].offsets[]`, which ADR-0164 §1 defines in pixels). A figure's
bounding box is the placed extent; unplaced members are dropped from the
figure and reported, never drawn at a guessed position and never silently
blanked (same rule as ADR-0164 §3 for missing pixels).

The reference implementation is `shape_layout` / `shape_image` in
`scripts/spike_compose_scene.py`; folding it into `compose_engine.Pack`
(the host-free Model of ADR-0165) is the implementing slice's job, with the
existing headless suite pattern (`scripts/test_compose_engine.py`) covering
it against a synthetic pack.

### 3. Step 3 is a heuristic and is labelled as one

The occupied-slot refusal is the only defence against a group's poses
overlapping, and it is not derivable from recorded data. It must carry that
caveat in the code that implements it, and a figure whose walk left members
unplaced must surface the count to the artist rather than look complete.

Making this exact needs the recorder to record pose membership — which OAM
entries appeared in the same frame — which is a bootstrap change and a
different ADR (ADR-0170, `proposed`). This ADR shipped the heuristic instead,
on the grounds that it "already turns striped noise into recognisable
characters" and that the exact version "cannot be had without re-recording
every pack". S10.a falsified the second half of that reasoning twice over:
the walk recovers 6.7 % / 10.5 % of a character's poses, not one clean pose
per group, and the data needed is already in memory at save time
(`HdPackBuilder::_oamFrames`), so the exact version costs one new sidecar
written from a stream the recorder already holds — no new capture, no PPU
change. Only newly recorded packs get it, which is the ADR-0153/0160
no-migration position anyway. What survives of the first half is weaker and
still true: a fragment is more legible than a node.

### 4. Export is unchanged

A composed sprite band still exports as a `usrNNN` sidecar of kind
`sprite` per ADR-0164 §3: `cells[]` at composed positions, `metatile` and
`tiles[]` per cell, `"composed": true`, `seed`/`locked`/`band`. Composing
figures changes which cells land where, not the file. `mep_build.py` needs
no change, and a sheet composed this way loads exactly as one composed
node-by-node does.

`seed` and `locked` continue to name **nodes** — a figure is identified by
its anchor node, so a reopened session resolves the figure from the anchor
through the same group sheet. No new field.

## Consequences

- The editor's gradeado, suggestion list and preview all change shape: cells
  become variable-sized (a figure is 16×16 to 40×40, not a uniform 8×8), so
  the View's fixed-cell layout and hit-testing are rewritten, not adjusted.
  The MVVM split of `compose_viewmodel.py` is what makes this affordable —
  the gesture state machine and its headless tests survive; the cell
  geometry is View code.
- Ranking gets a denominator question this ADR does not settle: `sprite_rank`
  scores nodes, and a figure has many. Summing member scores favours big
  figures, averaging favours small ones. The implementing slice must pick
  one and state it; the spike sidestepped it by not ranking at all.
- Groups of one stay first-class, so nothing that composes today stops
  composing.
- Packs recorded before ADR-0164 have no `sprNNN` `evidence[]` with usable
  counts and fall back to node composition, striped as before. Consistent
  with the ADR-0153/ADR-0160 no-migration position.
- The Phase 9 acceptance for the sprite layer (ADR-0164 Consequences: "the
  sprite band containing Ryu's bottom edge must rank the ground enemies
  above any projectile") is unaffected as written — it ranks, it does not
  say at what granularity — but its human counterpart, "the composed band
  looks like a scene", only becomes passable with this change.
- Two findings surfaced alongside the spike and are **not** decided here:
  screen-fixed HUD tiles polluting `floors[]` bands, and recorded packs
  whose vocabulary is dominated by title/menu art because the recording
  never reached gameplay. Both are recorder-side and each needs its own
  treatment.
