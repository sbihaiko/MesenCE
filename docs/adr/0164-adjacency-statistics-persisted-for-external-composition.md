# ADR-0164: The bootstrap persists its adjacency statistics in `sheets/adjacency.json`, and the composition editor works in layers by sheet kind, so an artist can compose, lock and re-slice a scene

- Status: accepted (2026-09-07, by the user; PRD Part A slice F9.17)
- Date: 2026-09-07
- Related: ADR-0153 (§2 grouping criterion, §3 sheet table incl. the
  `sprites.png` vocabulary sheet added 2026-09-07 as F9.16, §4 sidecar
  schema and precedence, §5 host-free modules), ADR-0154 (external repaint
  reads the same sidecars), ADR-0156 (screens own cells), ADR-0160
  (`sheets/` is the front door), ADR-0161 (palette variants are positional),
  ADR-0049/ADR-0147 (`auto/` is the recorder's folder, `mep/` the artist's)
- Supersedes / amends: amends ADR-0153 §4 (one more sidecar under `sheets/`;
  readers skip `"kind": "adjacency"`) and §3's file table.

## Context

The bootstrap already measures which tiles sit next to which, in two
independent places:

- **Background.** `MetatileVocabulary::BuildVocabulary` walks the *distinct
  stable screens* (`SelectStableScreens` → `DistinctOnly` over the retained
  `GridFrame`s) and, per screen, `AccumulateScreen` counts every east/south
  metatile pair into `Vocabulary::East`/`South` (directed counts between
  vocabulary indexes, remapped by `RemapAdjacency`). A count of 12 therefore
  means "on 12 distinct screens", not "in 12 frames". (The older
  `HdPackBuilder::AccumulateCoOccurrence` is a separate F5.4e path over raw
  8×8 shapes that only feeds the inert `# inferred … tileNearby` comments;
  it is not this ADR's source.)
- **Sprites.** `SpriteGrouping::Accumulate` walks the retained, de-duplicated
  `OamFrame` stream and counts, for every pair of OAM shapes, how often they
  were seen at each relative pixel offset, plus how often each shape appeared
  at all.

`SheetGrouping::SelectPredictiveEdges` and `SelectSpriteEdges` then apply
the ADR-0153 §2 test (count >= 3, both conditional probabilities >= 0.80)
and only the *surviving* edges reach disk, as `evidence[]` inside the
`objNNN.json` / `sprNNN.json` they produced. Everything that failed the
test, and the denominators the test divided by, is discarded at save time.

That is enough to emit a fixed set of sheets. It is not enough for the tool
the artist actually wants: start from one cell, see what statistically
touches it and where, lock a neighbour, have the remaining suggestions
re-ranked *conditional on the locked set*, and end up with a composed image
to paint (by hand or through `scripts/sheet_repaint.py`) that
`scripts/mep_build.py` slices back into `hires.txt` exactly like an object
sheet. Re-ranking under a lock is `P(B at offset d | the locked cells)`,
which needs the pairs that scored 0.3 as much as the ones that scored 0.95,
and needs the per-node totals. Recomputing them means re-recording; the
statistics were there and were thrown away.

Two facts about the existing sidecars shape the format:

- **A vocabulary index is not a `metatiles.json` cell.** The vocabulary has
  every metatile the recording saw (465 on the Ninja Gaiden reference pack);
  `metatiles.json` shows far fewer (154 there), because `hud`/`font`/`misc`
  cells go to their own sheets (ADR-0153 §3), cells a captured screen owns
  are routed off the sheet entirely (ADR-0156), and the alias pass (F9.7)
  folds look-alikes into one cell's `aliases[]`. A sheet cell carries
  `"metatile"` (its vocabulary index) and, when it absorbed others, their
  indexes under `aliases[].metatile`; a routed cell appears in no sheet.
- **Sprites had no vocabulary on disk until F9.16.** Only grouped shapes
  reached `sprNNN.json`; a lone projectile existed in `textures/chr/` alone.
  `sprites.png` / `sprites.json` (ADR-0153 §3, 2026-09-07) now lists every
  OAM shape, and this ADR depends on it.

Non-goals:

- No new runtime construct. The emulator never reads the file; a composed
  sheet is an ordinary `object`/`sprite` sidecar to the loader and to
  `mep_build.py` (same rule as ADR-0153 §6 for maps).
- No GUI inside Mesen in this slice. The consumer is an external script or
  web tool over `auto/textures/sheets/`.
- Not a different grouping criterion. The `objNNN`/`sprNNN` sheets the
  builder emits do not change; the file is *additional* evidence.
- No frame-level log. The file holds aggregates over the retained sample
  (`kMaxSheetFrames`, ADR-0153 §5), not a replay.

## Decision

### 1. One sidecar per pack: `textures/sheets/adjacency.json`

Written by `HdPackBuilder::SaveHdPack` next to the other sheets whenever the
sheet pipeline runs, from the same `Vocabulary` and `OamFrame` stream that
produced them. Node ids are **absolute vocabulary indexes** — `East`/`South`
keys for background, `BuildSpriteVocabulary` order for sprites — the same
numbers `cells[].metatile`, `aliases[].metatile` and `evidence[].a/b`
already use. Every node also carries its own `tiles[]` (the exact
`hires.txt` keys, same encoding as `cells[].tiles`), so the file is
**self-contained for keys**: a composed sheet copies `tiles[]` from the node
and never has to find which sheet, if any, shows that index.

```json
{
  "version": 1,
  "kind": "adjacency",
  "background": {
    "vocabulary": "metatiles.json",
    "vocabularySize": 465,
    "gridUnit": 16,
    "distinctScreens": 15,
    "nodes": [
      { "cell": 0, "count": 14, "context": "scene", "outE": 13, "outS": 14, "inE": 12, "inS": 14,
        "tiles": [ { "tile": "<32 hex>", "palette": "0F162A30" } ] }
    ],
    "edges": [ { "a": 127, "b": 137, "dir": "E", "count": 12 } ]
  },
  "sprites": {
    "vocabulary": "sprites.json",
    "vocabularySize": 212,
    "oamFrames": 3187,
    "nodes": [
      { "cell": 16, "appearances": 3012,
        "floors": [ { "bottom": 176, "count": 2890 }, { "bottom": 144, "count": 122 } ],
        "tiles": [ { "tile": "<32 hex>", "palette": "0F162A30" } ] }
    ],
    "pairs": [
      { "a": 16, "b": 17, "coFrames": 3012, "count": 3012,
        "offsets": [ { "dx": 0, "dy": 8, "count": 3012 } ], "other": 0 }
    ]
  }
}
```

- **Sampling is stated per block, not in the header.** `distinctScreens` is
  the universe a background `count` lives in (a cell seen on 12 of 15
  screens is common); `oamFrames` is the number of retained, de-duplicated
  OAM frames a sprite `appearances` lives in. A single `retainedFrames` at
  the top would make one of the two read as a fraction of the wrong thing.
- **Background edges are complete.** Every directed `East`/`South` entry
  with `count >= 1` is written: `a` at `(0,0)`, `b` one cell east or south.
  The map is already bounded by the vocabulary, not by frames, so there is
  nothing to prune. `nodes[].outE/outS/inE/inS` are the `Degrees` sums over
  that same complete map, so `sum(edges.count where a==X, dir==E) == outE(X)`
  holds exactly and a reader recomputes ADR-0153 §2's `pAB`/`pBA` without
  summing the list. `count` and `context` mirror the vocabulary entry.
- **Sprite pairs are pruned, denominators are not.** One entry per unordered
  pair `a < b` (matching `SelectSpriteEdges`), `dx`/`dy` in **pixels**, `b`
  relative to `a`, and — like `SpriteGrouping::Accumulate`, whose numbers
  these are — only offsets within `kSpriteMaxOffset` (32 px) on both axes.
  The histogram keeps the top `kAdjacencyMaxOffsets` (8) offsets by count
  and folds the rest into `other`, so a bullet drifting past everything
  costs a few bytes. A pair whose total `count` is below
  `kAdjacencyMinPairCount` (2) is not written — one co-sighting is noise
  and would make the file scale with frames. `nodes[].appearances` is the
  **unpruned** total, so `P(b at d | a)` computed from a written pair is
  exactly the value `SelectSpriteEdges` saw; the pruned mass is simply
  absent from the numerator side.
- **The offset histogram answers "figure" questions only.** Two limits make
  it useless for "who shares the floor": the 32 px cap drops a pair the
  moment the actors are further apart than that, and a horizontal approach
  spreads one relationship (`dy` constant, `dx` changing every frame) over
  dozens of `(dx, dy)` cells, each seen once or twice, which the top-8 fold
  then buries in `other` with its `dy` lost. Floor sharing therefore gets
  its own statistics, accumulated at save time from the same `OamFrame`
  stream with **no distance cap**:
  - `nodes[].floors[]`: per shape, a histogram of the **bottom edge** of the
    OAM entry (`Y + 8`; an 8×16 sprite's lower half lands on the true
    bottom) quantised to 8 px, top `kAdjacencyMaxFloors` (8) bands by count.
    This is the marginal `ΔY` distribution the review asked for, taken per
    node rather than per pair so it costs `O(nodes)`, not `O(pairs)`.
  - `pairs[].coFrames`: frames in which both shapes were on screen at all,
    any distance. A pair that never shares a frame (a boss and a first-level
    enemy) has no `pairs[]` entry regardless of floors; a pair with high
    `coFrames` and overlapping `floors[]` bands is the "same platform, same
    moment" the §5 sprite layer is built from. `coFrames` is written for
    every pair with `coFrames >= kAdjacencyMinPairCount`, so a pair may
    exist with `count: 0` and an empty `offsets[]` — actors that share
    scenes but never come within 32 px of each other.

  Two-actor floor sharing is then `coFrames(a, b)` weighted by the overlap
  of their `floors[]` bands, with the 8 px quantum absorbing the height
  difference between a tall and a short actor standing on the same ground.
  The band a `usrNNN` layer records (§5) is one such quantised bottom.
- Deterministic order (nodes by index, edges by `(a, b, dir)`, pairs by
  `(a, b)`, offsets by count then `(dx, dy)`), so two saves of the same
  recording produce byte-identical files and `content_id` (ADR-0139) does
  not churn.
- **Two query surfaces, deliberately separate.** The offset histogram
  answers near-field questions the builder also asks ("what sits above
  this shape", "what trails it by 8 px"); `floors[]` + `coFrames` answer
  the far-field one ("who stands on this ground while this shape is on
  screen"). §5's sprite layers use the second; the first draft tried to
  read them off the first and could not, for the reasons stated above.

The serializer lives beside `SerializeSheet` in `SheetRender` (host-free,
unit-tested in `core_unit_tests` Bloco P); `HdPackBuilder` only writes the
bytes, per ADR-0153 §5.

### 2. Readers skip it without a warning

`scripts/mep_build.py`, `scripts/sheet_repaint.py` and
`scripts/sheet_report.py` all read `sheets/*.json`. The first two warn on an
unknown `kind`; both add `adjacency` to their skip list silently — it is not
a sheet, it has no `sheet`/`cells`, and a warning on every pack would train
users to ignore warnings. `sheet_report.py` and `scripts/gameplay_probe.py`
already select by known kinds and are unaffected, but `sheet_report.py` is
named here so a future inventory column does not count it as a sheet. This
is the only change to the existing consumers.

### 3. A composed sheet is an ordinary `object` / `sprite` sidecar

The external tool's output contract is ADR-0153 §4 as it stands: a
`<name>.png` at the pack's scale, a `<name>.orig.png` twin, and a sidecar
with `"kind": "object"` or `"sprite"`, `cells[]` at the composed positions
(gutter 1), each cell's `metatile` and `tiles[]` copied from the
`adjacency.json` node, and `evidence[]` listing the edges the artist locked
(same shape as the builder's, with `pAB`/`pBA` recomputed from the file).

**Pixels for the twin.** The 1x pixels of a node come from whichever sheet
shows it: the cell whose `metatile` or `aliases[].metatile` equals the node
id, in `metatiles`/`hud`/`font`/`misc` for background or `sprites` for OAM,
copied nearest-neighbour from that sheet's `*.orig.png`. A background node
no sheet shows is one a captured screen owns (ADR-0156): the tool takes it
from the `backgrounds/screenNNN.orig.png` the routing named, or, failing
that, renders it from `textures/chr/` by its `tiles[]` keys. It must never
silently substitute a blank.

Two additions, both optional and ignored by `mep_build.py`:

- `"composed": true` — the sheet was assembled by a tool, not emitted by
  the builder, so a later bootstrap that rewrites `sheets/` is known to
  have removed it (see Consequences).
- `"seed": <node id>` and `"locked": [<node ids>]` — the session state, so
  the tool can reopen its own sheet.

**File name and precedence.** Composed sheets use the prefix `usrNNN`
(`usr000.png/.json/.orig.png`). `_SHEET_RANK` keys on `kind`, so a `usr*`
sheet takes the `object`/`sprite` rank (4); a tie against a builder sheet
claiming the same tile key resolves by ADR-0153 §4 — painted beats
untouched, then sidecar file name, **later wins** — and `mep_build.py` loads
sidecars in `sorted()` order, so the prefix has to sort after both `obj` and
`spr`: `'u' > 's' > 'o'`. (`cmp`, the first draft's choice, sorts *before*
`obj` and would have lost every tie to the very builder sheet the artist
was replacing.)

### 4. Where the composed sheet lives

Under `auto/textures/sheets/`, next to its inputs, **as long as the artist
has not painted it**: it is derived data and `bootstrap_auto_packs.sh` is
allowed to wipe `auto/textures`. The moment it is painted it is the
artist's work and belongs in `mep/textures/sheets/` (ADR-0147), which the
bootstrap never touches; `mep_build.py` already reads sheets from
whichever pack folder it is pointed at. An AI repaint of a composed sheet
follows ADR-0154 unchanged: `auto/repaint/`, labelled `generated`.

### 5. The composition editor is a layered canvas, one layer per sheet kind

The external tool this ADR exists for opens a *scene*, not a sheet: a
canvas the size of a screen (or of a stitched map region) built as a stack
of layers, each layer bound to the sidecar kind it came from and saved back
to it. The layer model is the artist's, the slicing is unchanged:

| Layer | Source sidecar(s) | Saved back to |
|---|---|---|
| HUD | `hud.json`, `font.json` | the same sheets (cells edited in place) |
| Background | `map-NNN.json`, `metatiles.json`, a `screenNNN` capture | the same sheets; a screen stays a `<background>` |
| Objects | `objNNN.json` | the same sheets |
| Sprites, one layer per **Y band** | `sprites.json` + `adjacency.json` | `usrNNN` (kind `sprite`), one per band the artist keeps |

Splitting HUD, background and objects is nothing new — ADR-0153 §3 already
separates them by context, and `mep_build.py` treats every sidecar
independently, so a layered editor over them needs no pipeline change.

**The new idea is the sprite layer.** The builder's `sprNNN` groups shapes
that hold a constant offset — a *figure*. A scene needs a second grouping:
shapes that share a **floor** — the hero and what it faces, the enemies
walking the same platform. That is a query over `sprites.nodes[].floors[]`
(which bottom bands a shape stands on) joined with `sprites.pairs[].coFrames`
(which shapes are on screen together), ranked by `coFrames × band overlap`;
the editor materialises one layer per band it finds. Seed-lock-recompute
(Context) operates inside a layer: locking a shape re-ranks the band's
remaining candidates by the same score conditioned on the locked set, and
the near-field `offsets[]` histogram then places a candidate's *figure*
(its `sprNNN` group) relative to the locked ones when one exists.

Two NES facts the band criterion must respect:

- OAM `Y` is the sprite's **top**. A 24 px enemy and a 16 px one on the same
  floor have different `Y`; the alignment that means "same floor" is the
  **bottom edge**, which is why `floors[]` is accumulated on `Y + 8` per OAM
  entry and quantised to 8 px — the lowest cell of any figure lands in the
  ground band whatever the figure's height, and the 8 px quantum is the
  tolerance.
- 8×16 sprites arrive as two 8×8 halves (ADR-0153 §5). Only the lower half
  reaches the ground band; the editor reads the band of a *group* as the
  band of its lowest cell, never of a lone upper half.

A layer the artist paints is saved by kind: HUD/background/object layers
write into the builder's own sheets (and then belong in `mep/`, §4); a sprite
band the artist keeps is exported as a `usrNNN` sidecar (§3) with
`"composed": true` and, in addition to `seed`/`locked`, `"band": { "bottom":
<px>, "tolerance": 8 }` so the tool can rebuild the layer from the same
`adjacency.json`.

Not a runtime concept: the emulator draws no layers from this. If HUD,
background and sprites ever become separate *rendered* planes of a pack,
that is a `hires.txt` format change (ADR-0004 is at v1-draft) with its own
`HdNesPack` rendering work, in the mould of ADR-0149's border layer — a
different ADR.

## Consequences

- One more file per pack. Sized on the Ninja Gaiden reference pack (465
  background nodes, 212 sprite shapes): nodes with `tiles[]` are the bulk,
  on the order of `metatiles.json`'s 80 KB, i.e. roughly 100 KB total with
  `floors[]` and `coFrames`; the edge/pair lists are smaller. The `tiles[]`
  duplication against the sheet sidecars is accepted on purpose: it is what
  lets a node that no sheet shows (routed to a screen, ADR-0156) still be
  resolved to `hires.txt` keys without a second lookup path, and 100 KB is
  under one captured `screenNNN.png`.
  No change to `hires.txt`, `pack.json`, or `content_id` for existing packs
  (a pack re-bootstrapped gains the file and its `content_id` changes once,
  as any re-bootstrap does).
- Existing `auto/` packs do not have the file until re-recorded. That is the
  ADR-0153/ADR-0160 position (no in-place migration); the tool reports
  "no adjacency.json — re-run the bootstrap" rather than falling back to
  the thin `evidence[]`.
- The file cites vocabulary indexes, so it only means something next to the
  sheets it was written with. The check is `vocabularySize` against the
  largest `metatile` seen across the named vocabulary's sheets (never
  `cells.length`, which is smaller by design), and every `metatile` in a
  composed sheet must be `< vocabularySize`.
- `HdPackBuilder` grows one write call; ADR-0155's header tracking makes the
  rebuild ordinary. The serializer lands in the existing `SheetRender.cpp`,
  so no `Core.vcxproj` entry (ADR-0007) is needed.
- The composition editor (§5: layered canvas, seed → ranked neighbours →
  lock → recompute → export `usrNNN`) is a separate slice with two
  acceptance tests: seed on a Ninja Gaiden metatile that `obj000.json`
  groups, lock its strongest neighbour, and the recomputed ranking must
  place the rest of `obj000`'s cells first; and the sprite band containing
  Ryu's bottom edge must rank the ground enemies of the recording above any
  projectile. This ADR guarantees the data the editor needs is on disk, the
  layer model it saves through, and that its output is legal input to the
  existing pipeline; it does not ship the editor.

## Revision (2026-09-07, same day, after review)

The first draft was checked against the code and corrected on seven points,
all kept here so the reasoning is auditable: (a) the composed-sheet prefix
`cmp` sorted before `obj`/`spr` and lost every tie — now `usr`; (b) it
assumed a sprite vocabulary sheet that did not exist — F9.16 added
`sprites.png/.json` first; (c) it validated against `cells.length`, which
never equals the vocabulary size — now `vocabularySize` and per-node
`tiles[]`; (d) it named `AccumulateCoOccurrence` as the source of
`East`/`South` — it is `AccumulateScreen` over distinct stable screens;
(e) it said both "every pair with count >= 1" and "pairs below 2 are
dropped" — now complete for background, pruned for sprites with unpruned
denominators; (f) one `retainedFrames` header misdescribed both universes —
now `distinctScreens` and `oamFrames` per block; (g) `sheet_report.py` was
missing from the reader list.

Extended the same day with §5 (the layered editor model) after the user
proposed separating HUD, background and objects into layers and grouping
sprites that share a Y axis into one layer. A second review the same day
showed the first version of §5 could not be computed from the offset
histogram: `SpriteGrouping::Accumulate` drops any pair beyond
`kSpriteMaxOffset` (32 px) on either axis, and a horizontal approach
scatters one floor relationship over dozens of `(dx, dy)` cells that the
top-8 fold loses. §1 gained `nodes[].floors[]` (bottom-edge bands, no
distance cap) and `pairs[].coFrames` (co-presence, no distance cap) for
that query, and §5 was rewritten on top of them. The same review's payload
concern (per-node `tiles[]` ≈ `metatiles.json` again) is answered in
Consequences; its `mep_build.py` point describes the state §2 changes, not
a gap in §2.
