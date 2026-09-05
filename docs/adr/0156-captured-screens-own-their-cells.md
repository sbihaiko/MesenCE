# ADR-0156: A captured screen owns the cells it covers — they leave `metatiles.png`

- Status: proposed
- Date: 2026-09-05
- Related: PRD Part A §4 "Phase 9" (slice F9.9, and the 2026-09-05 scrutiny
  against a target mockup), ADR-0050, ADR-0153 §3/§4/§5, ADR-0049, ADR-0005
- Supersedes / amends: amends ADR-0153 §3 (the scene sheet is no longer the
  whole scene vocabulary — the cells the screen surface owns are left off it)
  and ADR-0050 (its screens stop being a parallel artefact and become the
  primary surface for the content they cover)

## Context

`<background>` is the only **positional** surface the HD Pack format has. A
`<tile>` entry is keyed by tile content, so painting it paints every appearance
of that tile everywhere; `metatiles.png`, `objNNN.png` and `sprNNN.png` are all
content-addressed the same way. An element that spans many repeats of one tile —
a logo across a ring canvas, a crowd that does not tile — can only exist in a
`<background>`. ADR-0050 already writes one per static screen
(`backgrounds/screenNNN.png`, three `tileAtPosition` anchors, priority 20).

Two measurements made this urgent.

1. **The Punch-Out!! scrutiny (PRD, 2026-09-05).** Against an artist's HD
   reimagining, the missing capability was not grouping — mutual predictability
   already isolates Glass Joe and both of Little Mac's poses — it was that the
   pipeline never routes anything to the one positional surface it emits.
2. **F9.8's cost.** With adjacency evidence required before stitching, **23 of
   the 30 recorded packs write no map at all**. For those games
   `backgrounds/screenNNN.png` is the only whole-screen art surface in the pack,
   and Punch-Out!! is one of them.

The load-bearing rendering fact is in `HdNesPack::GetPixels`: the priority-20
layer (`BehindFgSpritesPriority`) is drawn **after** the background tile. So
wherever a captured screen's `<background>` draws, the tiles under it are not
the pixels that reach the display. A cell whose every sighting sits under such a
screen is therefore paint the artist can never see — and today it still costs a
cell on the contact sheet, next to the cells that do matter.

Non-goals: changing what `CaptureScreen` captures, or its anchors; a new
`hires.txt` construct; any change to the sidecar schema (ADR-0153 §4 stands
unchanged — this decision removes cells from a sheet, it does not describe them
differently); renumbering the vocabulary; touching maps, objects or sprites.

## Decision

### 1. Screen residency

A vocabulary entry is **screen-resident** when all three hold:

1. its context is `scene` (ADR-0153 §3);
2. at least one **captured** frame — a `GridFrame` the recorder flagged after
   `CaptureScreen` actually wrote `backgrounds/screenNNN.png` — shows it; and
3. **every** sighting of it in the whole retained grid stream is *explained*:
   some captured frame carries that same cell at the same `(row, col)` **and**
   at the same `FineX`.

A sighting is the tuple `(cell, row, col, fineX)`. Position and fine scroll are
both part of the identity because the surface is positional: the same cell one
column left, or the same column at another sub-tile offset, is a different
pixel, and the screen PNG does not cover it.

Screen-resident cells are **left off `metatiles.png`**. They stay in the
vocabulary with their index unchanged — maps, objects, sprites and the F9.7
alias list all address entries by index (ADR-0153 §4) — and the count is logged
by `HdPackBuilder::BuildSheets` (`N cells routed to the captured screens`).

### 2. Why those exact clauses

- **"Every sighting", not "seen on a screen".** A cell that appears on a
  captured screen *and* during gameplay must stay: the gameplay appearance is
  not under any `<background>`, so its tiles do render. One unexplained sighting
  disqualifies the cell. This is the clause that keeps Super Mario Bros.' ground
  block on the sheet.
- **The fine scroll.** It is what separates a non-scrolling game from a
  scroller when positions alone cannot. A scroller re-shows the same cells at
  the same grid positions under seven other sub-tile offsets;
  `RecordGridFrame` normalises the grid *relative to* `FineX`, so the offset is
  exactly the evidence that the picture moved.
- **Position, not just frame identity.** Punch-Out!! draws its fighters in the
  background layer. They move; the ring does not. The positional clause routes
  the ring and keeps the fighters on the sheet — which is precisely the split
  the mockup asks for ("route the static screen there, leave the moving subjects
  to tiles").
- **`scene` only.** A status bar sits inside every captured screen, so an
  unrestricted rule would empty `hud.png` and `font.png`, the two sheets whose
  whole point is that the artist finds the HUD without hunting. `misc` is the
  noise budget PRD Phase 9 validation test 7 measures and stays measurable.
- **A cell on several captured screens is still routed.** It is covered on all
  of them, so painting it on the sheet is invisible on all of them. The cost —
  the artist paints N screens instead of one crop — is real and is accepted in
  Consequences.

### 3. Nothing depends on those cells being on the sheet

`scripts/mep_build.py build` regenerates `textures/hires.txt` from the sheets
alone, so a key no sheet claims gets no `<tile>` — the pack renders that tile
from the ROM instead. That is already true today for every key outside the
vocabulary (the CHR static-export entries, for one); this decision enlarges the
set, it does not create it. It is safe for exactly the reason the rule was
written: a routed cell was never seen anywhere a captured screen did not already
cover it.

The screens themselves survive a rebuild untouched — `_parse_source` keeps
`[cond]<background>` lines in the body and `build` copies a missing background
PNG up from `auto/textures/` — so the surface the cells were routed *to* is
intact. `scripts/test_mep_build.py` pins all three facts
(`screen_residency_tests`).

**ADR-0153 §4 needs no new precedence clause.** Precedence resolves a key two
sheets both claim; this decision only removes a claimant. The rank table, the
painted/untouched probe and the alias fan-out are unchanged.

### 4. Where it lives

`MesenSheets::MarkScreenResidentCells` in
`Core/NES/HdPacks/MetatileVocabulary.{h,cpp}`, called at the end of
`BuildVocabulary` (after `MarkIsolatedAsMisc`, since residency is a scene-cell
decision and that pass is what makes a cell stop being one). Host-free, per
ADR-0153 §5 and ADR-0127. `GridFrame::Captured` and
`MetatileEntry::ScreenResident` are appended to `TileSheetTypes.h`;
`HdPackBuilder` sets the first when `CaptureScreen` grows
`_hdData.BackgroundFileData`, and `WriteContextSheets` reads the second.
Cases in `scripts/core_unit_tests.cpp` Bloco P (`make core-unit-tests`).

## Consequences

- **Measured, offline, on the 30-pack library** by
  `scripts/spike_screen_residency.py`, which matches `metatiles.orig.png` cells
  against the captured screens (palette-agnostic, alignment searched). It is an
  **upper bound** on the rule, not the rule: it cannot see the motion frames,
  which is where clause 3 does its work. Mike Tyson's Punch-Out!! 71 of 334
  cells sit on exactly one screen and 182 on several (21 % / 55 %); Super Mario
  Bros. 50 of 92 and 24 (54 % / 26 %); Metroid 7 of 62 and 37 (11 % / 60 %).
  Library-wide, 1258 of 4542 cells sit on exactly one captured screen. The
  scrollers' numbers are the inflated ones by construction — SMB's ground block
  is on its captured screen *and* under every scroll offset of the level, and
  only the recorder can tell those apart. **No pack was re-recorded for this
  slice**, so the shipped rule's real numbers are not known yet.
- **An artist repaints screens, not crops, for routed content.** A cell on
  twelve captured screens now costs twelve painted screens. That is the honest
  price of a positional surface, and it is the workflow ADR-0050 measured the
  best community packs actually using.
- **The anchor gap.** A `<background>` is condition-gated on three
  `tileAtPosition` anchors. On a *variant* of a captured screen where an anchor
  tile changed, the background does not draw and the routed cells render
  vanilla — visibly flatter than the painted neighbours around them. The rule
  cannot see this: it tests positions, not whether the conditions hold. Bounded
  to variants of screens the recording did capture, but real, and the cheapest
  fix if it bites is to widen the anchor choice, not to widen the rule.
- **A thin recording routes too much.** A session that never leaves one screen
  captures it, sees nothing else, and routes its whole vocabulary — the pack
  then ships an almost empty `metatiles.png`. `scripts/sheet_report.py` is how a
  bad recording is told from a bad inference (ADR-0153 already says so); the
  builder's new log line makes it visible without opening the pack.
- **Cost at save time.** One extra pass over the retained grid stream
  (≤ `kMaxSheetFrames` frames × ≤ 240 placements) and one `std::set` of
  sightings. No per-frame cost.
- `GridFrame` grows one `bool`; the retention budget of ADR-0153 §5 is
  unchanged in practice (the struct is dominated by its 960 `uint16_t` cells).
