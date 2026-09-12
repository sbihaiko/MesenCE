# ADR-0175: A group sheet states its blank slots; it never fills them with a repeat

- Status: accepted (2026-09-12, at the user's request, with the fix
  implemented in the same turn); reflected in `Core/NES/HdPacks/`
  (`SheetGrouping`, `SheetRender`, `HdPackBuilder`) and in
  `scripts/core_unit_tests.cpp`
- Date: 2026-09-12
- Related: ADR-0153 (§3 the group layout, §4 the sidecar schema — a crop is
  keyed back to `hires.txt` by its tile key), ADR-0156 (§ routing: a cell a
  captured screen owns leaves the contact sheet), ADR-0166 (`screens[]` — the
  surface those cells are painted on instead), ADR-0171 (the same decision,
  taken for the composition editor's export preview), issue #175
- Supersedes / amends: amends ADR-0153 §4 — an object/sprite sheet sidecar
  gains an optional `emptySlots[]`

## Context

The Phase 9 validation panel (section 2, 2026-09-12) reported two gaps in
what the sheet surface offers an artist to paint, both on the Contra pack.
They have different answers.

**1. Sheets render with holes.** `spr016.orig.png` is a 6x2 grid carrying 6
cells and reads `GA M` / `OV R`; `obj000` fills 12 of 15 slots, `obj001`
9 of 12, `obj009`/`obj010`/`obj011` 3 of 4 each. The mechanism is
`SheetGrouping::PlaceMembers`: a group's grid is the **bounding box** of a
BFS layout at the members' own dominant offsets, so a figure that is not a
rectangle leaves slots nobody occupies. `obj009`'s three cells in a 2x2 box
is not a defect at all — it is an L-shaped subject. The defect is that the
pack says nothing, so an artist cannot tell a deliberate blank from a
subject the recorder failed to place.

(The `spr016` case has a second cause worth recording, which this ADR does
**not** fix: the letter `E` occurs twice in one frame ("GAME"/"OVER"), so its
own `appearances` denominator in ADR-0153 §2 is double every partner's count
and every edge from it is dropped. A tile that repeats within a frame cannot
currently join a group. Changing that is a change to the grouping criterion —
the option ADR-0174 rejected for the same reason — and needs its own
measurement.)

**2. Background vocabulary cells on no painting surface.** The panel reported
37 of 258 nodes unreachable; the issue corrected it to 14 after following
`aliases`. Recomputed here over `metatiles.json`, `misc.json`, every
`obj*.json` and both maps' `placements`, following `aliases` and each cell's
own `metatile` id: **14 of 258** — nodes 66, 70, 74, 78, 87, 116, 117, 118,
121, 122, 123, 124, 180, 237. The issue's figure is confirmed.

## Decision

### 1. The blank is stated, never filled

`MesenSheets::EmptyGroupSlots` (`Core/NES/HdPacks/SheetGrouping.{h,cpp}`,
host-free per ADR-0127) returns the slots of a group's `Columns x Rows` grid
that no member occupies, row-major, and the sidecar carries them when there
are any:

```json
{ "kind": "sprite", "columns": 2, "emptySlots": [{ "col": 0, "row": 0 }], "cells": [ ... ] }
```

`col`/`row` are in cells, the units the group lays its members out in, so a
consumer reaches the sheet pixels through the sidecar's own `cell` size and
`gutter`. The field is optional on read: absent, or present and empty, both
mean "no blank worth stating". A rectangular figure's sidecar is byte-for-byte
what it was.

**Filling the slot with the cell that would repeat there is rejected.** A
sheet crop is keyed back to `hires.txt` by its tile key (ADR-0153 §4); one key
can only carry one piece of art; an artist handed two crops of one key would
paint them differently and the rebuild would silently keep one. ADR-0171 took
this exact decision for the composition editor's export preview — a hole reads
"already painted next door", not "unpainted" — and the recorder's sheets are
the same substitution model.

### 2. Clause 2 is not a defect, and nothing changes for it

All 14 unreachable nodes are **screen-resident** (ADR-0156): every sighting
sat where a captured screen already shows it, so a `<background>` covers the
cell wherever it appears and a cell spent on it in `metatiles.png` would be
dead paint. That is why they are off the contact sheet, and ADR-0156 kept them
in the vocabulary on purpose, because indexes are addresses.

They are not on *no* painting surface. ADR-0166 put `screens[]` on exactly
these nodes in `adjacency.json`: the `screenNNN` each captured frame became
and the node's 8 px placement on it. Verified on the Contra pack — all 14 of
the 14 resolve to an existing `textures/backgrounds/screenNNN.orig.png`, at a
stated placement. The pack already says both where the art is painted and why
it is not on a sheet; the audit that produced "unreachable" did not count the
captured screens as a painting surface.

So the requirement "a cell the recorder puts in the vocabulary is reachable on
some painting surface, or the pack records why it is not" is already met, and
no code changes for it.

## Consequences

- A consumer can render a blank slot as deliberately blank. It still cannot
  learn *which* art would repeat there, because the recorder does not place a
  node twice and the layout never computed a second position for it.
- The sidecar grows by one short array on non-rectangular groups only.
- A reader that validates the schema must ignore the new key rather than
  reject it, like ADR-0172's `index` and ADR-0174's `poses`.
- `EmptyGroupSlots` reads the `SheetGroup`, not the rendered cells, so it
  states what the layout decided. A member `RenderGroup` skips (a metatile
  index outside the vocabulary, which nothing produces today) would leave a
  blank the list does not name.
- **The `spr016` cause above stays open.** A tile that repeats inside one
  frame is excluded from every group, so the sheet is short a subject and not
  only short a slot. This ADR makes the hole legible; it does not put the `E`
  back.
