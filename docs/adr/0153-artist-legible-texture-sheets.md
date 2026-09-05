# ADR-0153: Artist-legible sheets — metatile vocabulary as the unit, mutual-predictability grouping, stitched maps as an artist surface

- Status: accepted
- Date: 2026-09-05
- Related: PRD Part A §4 "Phase 9", ADR-0050, ADR-0049, ADR-0147, ADR-0005,
  ADR-0043, ADR-0132, ADR-0007, MEP-v1 §5.1
- Supersedes / amends: amends ADR-0050 (the bootstrap's artist surface is no
  longer only `backgrounds/screenNNN.png`; it gains `textures/sheets/`);
  retires the F5.4e grouping criterion (co-occurrence union-find over
  "adjacent ≥ 2 times") described in `HdPackBuilder.h`, replacing
  `BuildObjectSheets`' clustering while keeping its inert
  `# inferred … tileNearby` output contract; **amended 2026-09-05** (§1 grid
  criterion, §3 `misc`/`hud` rules, §4 schema) after the first measurements on
  real recordings contradicted the criterion this ADR was accepted with;
  **amended 2026-09-05** again (§6 continuous cut rule, F9.12) after a title
  screen was found welded into a level map

## Context

The bootstrap's `auto/` pack is unreadable. `Chr_N.png` sheets are emitted in
CHR order: thousands of 8×8 fragments with no neighbourhood — half a logo, one
corner of a rock, a run of font glyphs. Next to a hand-made pack (the Zelda 1
reference `mep/`) the difference is not resolution, it is *subject*: the artist
sees whole bushes, trees and a stitched overworld; `auto/` shows noise.

F5.4e was meant to bridge that gap by inferring objects from spatial
co-occurrence, but its criterion — union-find over tile-shape pairs seen
adjacent at least twice — collapses any contiguous scene into one component, so
`textures/sheets/object*.png` was **never emitted on a real game**. The
2026-09-04 spike (`scripts/spike_tile_sheets.py`, env-gated grid dump in
`HdPackBuilder::OnFrameEnd`, evidence under `runs/spike-sheets/`) measured it:

| Game | F5.4e baseline | metatiles (aligned 2×2) | mutual predictability |
|---|---|---|---|
| The Legend of Zelda | 59/59 shapes in **one** component | 62 metatiles (bush, tree, rock, sand, forest edge), 5 screens stitched into one map | 0 objects (correct: an overworld *is* a field, not a figure) |
| Excitebike | 132/132 shapes in **one** component | 300 metatiles, 23 712 px continuous strip with ramps | 48 objects, largest 24 cells |

So the unit an artist recognises is not the 8×8 tile and not the whole screen:
it is the game's own building block (16×16 on a game with an attribute-aligned
grid, 8×8 when there is none), plus the *figures* built from those blocks, plus
the *map* they compose into.

Non-goals: a tile-map editor; a game-specific level format; any change to
`hires.txt` semantics (MEP `textures/` stays an envelope over HD Pack, ADR-0005);
a new runtime construct — stitched maps are a paint surface, the emulator keeps
rendering through `<tile>`/`<background>`; AI generation inside the emulator
(F9.6 stays an external script under its own ADR).

## Decision

### 1. The unit is the game's grid, detected automatically

A **metatile** is a 2×2 tuple of background tile *shapes* (`HdTileKey` with
`PaletteColors` wildcarded, as F5.4e already keys co-occurrence) at a fixed cell
parity. For each of the four phases `(x0,y0) ∈ {0,1}²` the builder counts the
**distinct** 2×2 tuples the distinct stable screens produce. The phase with the
fewest distinct tuples wins — a real grid repeats itself, an arbitrary cut does
not — and the margin is the decision:

```
phaseAdvantage = 1 - distinct(bestPhase) / mean(distinct(other three phases))
hasGrid        = phaseAdvantage >= kGridPhaseAdvantage (0.15)
```

The grid unit is **16** unless the recording yielded fewer than
`kMinMetatilePlacements (64)` aligned placements — a session spent entirely in
menus and text — in which case it falls back to **8** (each tile is then its own
one-cell "metatile"). `hasGrid` selects the *parity*, not the unit: a game with
no grid still reads better in 16×16 blocks than as loose 8×8 fragments.
Detection is automatic, never a user setting; the chosen unit, the phase,
`phaseAdvantage` and `hasGrid` are written to the sidecar JSON and to
`mesen.log`. Zelda 1 measures `phaseAdvantage` 0.34 (`hasGrid` true, phase
(0,0)); Excitebike measures 0.03 (`hasGrid` false). Both select unit 16.

*Amended 2026-09-05.* This ADR was accepted with

```
consistency(phase) = placements whose 2×2 tuple occurs >= 3 times / total placements
```

and a `>= 0.60` threshold on the winner. Measured on real recordings that
quantity saturates: 0.930–0.994 on Zelda, 0.954–1.000 on Excitebike, i.e. every
phase of every game clears 0.60, so it decided nothing — and the 8×8 alternative
scores *higher* than the 16×16 one by construction (a one-tile "tuple" repeats
far more often than a four-tile one), which is the opposite of what the §4
example below used to show. Two other candidates were measured and rejected:
compressivity (distinct tuples / placements) and neighbour determinism (mean
entropy of the east/south successor distribution); neither separated the two
golden games. Phase advantage separated them by 13×, so it is the criterion.
`kGridConsistencyThreshold` and the `gridConsistency` JSON field survive as
diagnostics only — they decide nothing.

### 2. Grouping is by mutual predictability, not by raw counts

Two adjacent metatiles A and B join an object only when, for a direction
`d ∈ {E, S}` with `n = count(A d B)`:

```
n >= kSheetMinPairCount (3)
  and n / out_d(A) >= kSheetMinPairProb (0.80)
  and n / in_d(B)  >= kSheetMinPairProb (0.80)
```

i.e. B is the usual thing east of A **and** A is the usual thing west of B.
Sand next to everything fails; a 2×2 boss door passes. Surviving edges feed a
DSU; components with `2..kSheetMaxObjectCells (32)` cells become objects, laid
out by BFS at their dominant offsets. The same test, applied to OAM entries that
move together frame to frame, produces sprite sheets (F9.5).

F5.4e's `# inferred … tileNearby` candidates keep their contract exactly:
inert definitions, never auto-attached to a `<tile>`, so a wrong grouping can
never make a tile fail to render (ADR-0050's "nothing inferred breaks
rendering" rule). Only the clustering criterion changes.

### 3. Sheets are for humans, and they are split by context

Under `<pack>/textures/sheets/`, every sheet is RGBA with a **transparent**
background, one **1-cell gutter** between cells, and **no baked labels** —
labels live in the sidecar JSON. Cells are grouped so a rupee counter never
sits between two trees:

| File | Contents |
|---|---|
| `metatiles.png` / `.json` | scene vocabulary (the paintable world) |
| `hud.png` / `.json` | cells seen only in the status-bar rows |
| `font.png` / `.json` | HUD-region cells whose tiles use ≤ 2 colour indexes |
| `misc.png` / `.json` | unaligned or *isolated* cells (the noise budget) |
| `map-NNN.png` / `.json` | one stitched region per connected map |
| `objNNN.png` / `.json` | one object (≥ 2 cells, mutual predictability) |
| `sprNNN.png` / `.json` | one sprite group (F9.5) |

Cells within a sheet are laid out **most-seen first** (`count` descending, ties
in vocabulary order): the blocks the game is actually built out of meet the
artist at the top of the sheet, and one-off title-screen art sinks to the
bottom.

*Amended 2026-09-05,* on the rules that did not survive contact with real
recordings:

- **`misc` is isolation, not rarity.** `count == 1 → misc` put 89 % of Zelda's
  vocabulary in `misc.png`, which makes the noise budget unreachable and the
  scene sheet empty. A cell is `misc` when it is unaligned, **or** when
  `count == 1` *and* it has no east/south neighbour that is a scene cell with
  `count > 1`. Zelda went 52.7 % → 3.2 % misc, Excitebike 28.8 % → 0 %.
- **A status-bar row is mostly frozen, not byte-identical.** Requiring a HUD
  row to be identical across every distinct screen finds nothing on any game
  whose HUD contains a score, a timer or a life counter — Super Mario Bros. and
  Contra were reporting zero HUD rows and spilling their digits into
  `metatiles.png`. A row is a status bar when it is blank on every screen, or
  when at least `kHudRowFrozenRatio (0.50)` of its columns are identical across
  screens *and* at least `kHudRowDrawnRatio (0.25)` of them are drawn (the
  second test is what keeps a stretch of sky, identical everywhere and empty
  everywhere, out of the HUD band). Super Mario Bros. went from 0 to 31 HUD
  cells, and 144 → 109 scene cells.
- **A status bar needs a quorum of the screens, not all of them.** The screen
  set is a whole recording, so a title card, an option menu and a results
  screen sit next to the gameplay screens and share no row with them — one
  such screen was enough to erase the HUD band of every game that had one.
  Excitebike's instrument panel and Metroid's energy bar were invisible for
  exactly this reason. A column now counts as frozen when its **most common**
  shape covers `kHudRowScreenAgreement (0.60)` of the screens, which is the
  previous rule at agreement 1.0 and tolerates a minority of unrelated
  screens. Measured on the installed screens of the golden games: at
  unanimity every row scores zero on all of them; at 0.60, Excitebike's four
  bottom rows, Super Mario Bros.' four top rows and Castlevania's top and
  bottom bands all resolve.

  The known false positive is a **frozen scenery band**: Excitebike's crowd
  stand is drawn identically on every race screen and passes both tests, so a
  slice of it lands on `hud.png`. The cost is bounded — the band still reaches
  the stitched map, and it is one cell — and no cheap test separates "frozen
  because it is a status bar" from "frozen because it is a repeating backdrop"
  without tracking scroll per row, which §1 deliberately does not do.

Each sheet gets its pixel-exact `*.orig.png` twin under the existing F5.4d
`_writeReferences` convention. `misc` exists so the noise budget (PRD Phase 9
validation test 7) is *measurable*: scene sheets stay clean, singletons are
isolated rather than interleaved.

### 4. Sidecar JSON schema (version 1)

Common envelope; `cells[]` is the slicing contract `mep_build.py` reads back:

```json
{
  "version": 1,
  "kind": "metatiles",
  "gridUnit": 16,
  "gridPhase": { "x": 0, "y": 0 },
  "hasGrid": true,
  "phaseAdvantage": 0.3447,
  "gridConsistency": { "chosen": 0.9938, "alt8x8": 0.9994 },
  "cell": { "w": 16, "h": 16 },
  "gutter": 1,
  "columns": 16,
  "sheet": "metatiles.png",
  "reference": "metatiles.orig.png",
  "cells": [
    {
      "index": 0,
      "x": 1, "y": 1,
      "count": 431,
      "context": "scene",
      "label": "",
      "tiles": [
        { "tile": "<32 hex chars>", "palette": "0F162A30" }
      ]
    }
  ]
}
```

`x`/`y` are the cell's top-left in sheet pixels; `tiles[]` is row-major inside
the cell (length 4 at `gridUnit` 16, 1 at 8) and carries the exact `hires.txt`
key of each 8×8 tile, so a crop maps back to tile entries with no guessing.
`"label"` is always emitted and always empty from the builder — it is the
artist's field, preserved by `mep_build.py`. `"hasGrid"` and `"phaseAdvantage"`
carry the §1 decision; `"gridConsistency"` is retained for diagnostics, and its
`alt8x8` member being the larger of the two is expected, not a bug.

**Precedence when two sheets claim the same tile key.** A cell claims a tile key
only when it was actually painted: the crop in `<sheet>.png` is compared against
the same cell of its 1x `*.orig.png` twin, with the twin upscaled by the sheet's
scale factor N. Different means the cell is edited and claims the key; identical
means it does not claim it. A painted cell always beats an untouched one,
whatever their kinds. Between two painted cells — and, when no sheet painted the
key at all, between the untouched ones, since the captured art still has to
reach `hires.txt` — the static kind rank decides (`metatiles` < `misc` < `map` <
`object`/`sprite` < `hud`/`font`, ties broken by sidecar file name, later wins).
A sheet with no usable twin (`"reference": ""`, a missing or unreadable file, or
a twin whose size is not exactly 1/N of the sheet) has nothing to diff against,
so every one of its cells counts as painted and it relies on its static rank
alone. Every override is logged, tagged `(painted)`, `(untouched)` or
`(precedence)`.

A static rank alone cannot work here: `map > metatiles` breaks PRD Phase 9
validation test 3 ("make every bush purple" from `metatiles.png`), and
`metatiles > map` breaks test 4 (the seam test, painted on the map). Only "who
actually painted this cell" satisfies both.

A map adds `"mode": "screen" | "continuous"`, `"hudRows"`, and a `placements[]`
list of `{ "x", "y", "cell" }` (map pixel origin → index into the metatile
vocabulary), which is how a painted map is sliced back into per-tile crops.
An object or sprite adds `"cells[].metatile"` (vocabulary index) and
`"evidence": { "dir": "E", "count": 7, "pAB": 0.9, "pBA": 0.86 }` per joined
edge, so a questionable grouping can be argued with instead of guessed at.

### 5. The analysis lives in host-free modules, the I/O stays in the builder

Following the ADR-0127 / ADR-0149-F8.3b precedent (`BorderLayout`), the
inference is **not** written inside `HdPackBuilder.cpp`. New files under
`Core/NES/HdPacks/`, none of which may include `pch.h`, `Emulator` or any
console type:

| File | Owns |
|---|---|
| `TileSheetTypes.h` | shared PODs: `SheetTileKey`, `GridFrame`, `MetatileKey`, `SheetCell`, `SheetImage`, `SheetPlacement` |
| `MetatileVocabulary.{h,cpp}` | stable-screen filter, phase/grid detection, vocabulary + counts, HUD/font/scene/misc classification |
| `ScreenStitcher.{h,cpp}` | screen-based and continuous stitching → `SheetPlacement[]` |
| `SheetGrouping.{h,cpp}` | mutual-predictability DSU, object/sprite layout |
| `SheetRender.{h,cpp}` | tile → RGBA, contact-sheet compositing with gutters and alpha, sidecar JSON serialisation to a string |

`HdPackBuilder` only feeds them the recorded grid stream and writes the bytes
they return (`PNGHelper::WritePNG`, `std::ofstream`). All five link into
`make core-unit-tests` and are added to `Core.vcxproj` (ADR-0007 drift guard).

The builder retains, during recording, a de-duplicated stream of per-frame
background grids: `GridFrame` = 30×32 `uint16_t` shape ids + the fine x-scroll,
consecutive duplicates collapsed, capped at `kMaxSheetFrames = 4096`
(≈ 8 MB). Sheet inference runs once, in `SaveHdPack`, never per frame.

### 6. Stitching mode is chosen from the data, and a map is never a runtime layer

The screen-based stitcher runs first (scroll direction inferred from an
early-transition frame, anchored on the last placed screen, re-anchored on
revisiting a known screen). When it places fewer than 2 screens **and** the
continuous stitcher (accumulated per-frame x-shift, cut on a match below 0.5)
spans more than 512 px, the continuous result is emitted instead; a cut always
starts a new `map-NNN.png`. Either way the map is a *paint surface*: nothing in
`hires.txt` references it, and `mep_build.py` slices it back into per-tile
crops via `placements[]`. The runtime keeps using `<tile>`/`<background>` only.

*Amended 2026-09-05 (F9.12).* "Cut on a match below 0.5" is not a sufficient
end-of-region rule, and this clause is replaced by a two-tier bar. 0.5 is
unreachable for the case that actually broke: Super Mario Bros.' title screen is
drawn on top of the very start of world 1-1 — same hill, same bushes, same
ground — with a logo panel and a menu stamped into the sky. Measured on the 21
stable screens that recording installed under
`auto/textures/backgrounds/screen*.orig.png`, compared cell by cell (8×8,
pixel-exact) at the shift the stitcher accepts, the title screen agrees with the
level's first screen over **0.700** of the playfield at `dx == 0` — the camera
genuinely did not move — while two consecutive level screens agree over
**0.996–0.999**. So no cut fired, `cum` stayed 0, and `PaintFrame`'s
first-writer-wins baked the logo, "ONE PLUMBER / TWO PLUMBERS" and
"TOP- 000000" into the level map's sky. There was no seam in `map-000.png`
because there was no offset: the two screens were superimposed on the same world
columns.

The rule is therefore: a step that **claims a shift** (a non-zero `dx` that
beats standing still by `kStitchStillMargin`, F9.8) is cut below `kMinMatch`
(0.5), exactly as before; a step that **does not** is a claim that both frames
show the same place, and is cut when the *still* score — the whole playfield at
`dx == 0` — falls below `kStitchWorldAgree` (**0.85**, the midpoint 0.848 of the
measured gap above, read off recorded evidence and not swept). A closed region
narrower than 512 px is dropped as before, so an overlay screen that is cut
loose disappears instead of becoming its own map.

Scrolling steps are deliberately left alone: that is what keeps Excitebike's
continuous track in one piece, by construction rather than by tuning. The
consequence is that a screen swap which *does* fabricate a plausible non-zero
shift is still governed by `kMinMatch` alone; no frame-level data exists to set a
second bar for that case without risking the one genuine continuous track on
record.

### 7. The spike's grid dump stays, as a debug flag

`MESEN_SPIKE_GRID_DUMP` is renamed `MESEN_SHEET_GRID_DUMP` and moves **out of
`OnFrameEnd`**: it is written once from the retained grid stream at
`SaveHdPack` time, in the format `scripts/spike_tile_sheets.py` already parses.
Threshold tuning is a human, per-game judgement (the Phase 9 validation panel
is qualitative), and iterating offline on a dump beats rebuilding the core.
The hot path keeps no dump code.

## Consequences

- The bootstrap gains a second artist surface next to ADR-0050's screens.
  The two are complementary: screens are what the game *showed*, sheets are
  what the game is *made of*. Neither is referenced by the other.
- Vanilla-looking sheet output stays in `auto/` (ADR-0049 / ADR-0147), so
  community art is never masked; an installed accepted pack still wins.
- `BuildObjectSheets`' output changes shape: `object<NNN>.png` becomes
  `objNNN.png` with a sidecar. Any `auto/` pack recorded before this ADR keeps
  its old files until re-recorded — there is no migration, `auto/` is
  regenerable by construction.
- Recording now costs up to ~8 MB of retained grids and one inference pass at
  save time. `kMaxSheetFrames` bounds it; a long session drops the tail, which
  costs late-game vocabulary, not correctness.
- Grid detection can pick 8 on a game that *does* have a 16×16 grid but was
  recorded almost entirely on non-aligned screens (menus, cutscenes). The
  failure mode is a larger, flatter vocabulary — legibility, never rendering.
- `hud.png` and `font.png` come out **empty on both golden games**: Zelda's HUD
  is 3 rows and a unit-16 metatile covers 2, so its third row leaks out of the
  band, and the `font` rule is HUD-region-scoped, so playfield text (Zelda's
  story crawl, Super Mario Bros.' title logo) stays in `metatiles.png`. The
  most-seen-first ordering keeps that text at the bottom of the sheet rather
  than interleaved with the terrain, which was judged good enough for Phase 9;
  a region-independent `font` rule is deliberately not adopted here.
- Everything in §1 and §3 above is decided **from the recording**, so a
  recording that never reaches gameplay produces a vocabulary of menus and
  title art. `scripts/sheet_report.py` (scene cell count, distinct screens,
  noise budget) is how a bad recording is told from a bad inference.
- Five new host-free files mean five new entries in both build manifests; the
  ADR-0007 check fails loudly if only one side is updated.
- `mep_build.py` gains a round-trip it must keep pixel-exact (PRD test 6): the
  identity round-trip of untouched sheets has to reproduce the captured screens
  under `scripts/headless_record`, which is the automated half of the otherwise
  human validation panel.
