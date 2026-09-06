# ADR-0161: The palette-variant correspondence is read positionally, not from the palette bytes

- Status: accepted (2026-09-06, by the user — record of a mechanism already in `scripts/sheet_repaint.py`; ADR-0154 §5 step 1 carries a pointer to it so the literal recipe is not reimplemented)
- Date: 2026-09-05
- Related: PRD Part A §4 "Phase 9" (slice F9.6), ADR-0154 §5, ADR-0153 §4
  (sidecar `cells[].tiles[].tile` / `.palette`), `scripts/sheet_repaint.py`,
  `Core/NES/HdPacks/SheetRender.h`
- Supersedes / amends: amends ADR-0154 §5 step 1 — the *result* it asks for is
  unchanged, the *source* the mapping is read from is stated here.

## Context

ADR-0154 §5 recolours a palette variant from a single generation. Step 1 of
its recipe is:

> From the 1x originals, read the canonical cell's palette colours and the
> variant cell's palette colours, **in NES colour-index order (0..3)**.

Index order is what makes the rest of §5 correct: index *i* of the canonical
palette must be paired with index *i* of the variant's, or the residual is
re-applied on top of the wrong colour and the variant comes out with its
colours permuted.

The script cannot literally do what that sentence says. A sheet is rendered
by `SheetRender.h` through `HdPackBuilder::_palette`, the emulator's
**configured** 512-entry master palette, which a user can replace. The
sidecar's `tiles[].palette` is a string of NES palette bytes
(`"0F20210F"`); turning one into the RGB that actually landed in the PNG
needs that master palette, and the tree carries no copy of it in Python
(`scripts/spike_tile_sheets.py` has a hardcoded one, but it is a spike's
fixed table and would silently disagree with any pack recorded under a custom
palette). So a palette byte does not name a colour on this side of the pipe.

The first implementation dodged the problem by reading each cell's distinct
opaque colours off the pixels and ranking them **by frequency**, pairing
canonical rank *i* with variant rank *i*. That is right most of the time and
wrong in a way nothing announces: the two cells share a bitmap, so each index
covers the same number of pixels in both, and two indexes that cover the same
count *tie*. The tie is then broken by RGB value — of each cell's own colours.
A canonical pair `(10,10,10)` / `(200,200,200)` against a variant pair
`(250,0,0)` / `(0,0,5)` ranks in opposite orders, and the recolour swaps the
two colours over the whole cell.

## Decision

The correspondence is read **positionally**, from the 1x originals:

- The two cells are members of one shape group. `shape_key` groups on the
  `tiles[].tile` tuple with the palette ignored, so both cells render the same
  CHR bitmaps; the pixel at offset `(dx, dy)` therefore carries the same
  2-bit colour index in both. **Same offset is same index**, exactly, with no
  master palette involved.
- `palette_correspondence(img, canon, variant)` walks the two cells in
  raster order and returns:
  - `canon_palette` — every opaque colour of the canonical cell, in
    first-appearance order. The nearest-colour search of §5 step 2 runs over
    *all* of it, including colours with no counterpart, so a generated pixel
    is never attracted to the wrong index merely because its own went
    unmapped;
  - `mapping` — canonical RGB → variant RGB where the evidence is
    unambiguous;
  - `missing` — canonical colours with no counterpart: the variant is
    transparent there, or one canonical colour was observed against two
    different variant colours (which means the two cells are not the same
    drawing, and §5's grouping assumption has been violated for that cell).
- `missing` colours degrade to identity — the generated pixel is left alone —
  and the degradation is announced **on stderr**, naming the sheet and cell,
  unconditionally rather than under `--verbose`. ADR-0154 §5 already says
  "says so on stderr rather than inventing a mapping"; gating it on a verbosity
  flag made the one case a person needs to hear about the quiet one.

This is a statement about *where the mapping comes from*, not about what §5
does with it: steps 2 and 3 (nearest canonical colour, keep the residual,
re-apply on the variant's colour, clamp, skip transparent) are unchanged, and
so is `--no-variants`.

## Consequences

- The recolour is exact rather than nearly right, and it stops depending on a
  frequency ranking whose tie-break is decided by colours that have nothing to
  do with the index they sit at. `scripts/test_sheet_repaint.py` covers the
  tie case directly; on the pre-change code the two colours came out swapped.
- The disagreement case is now detected rather than approximated. Ranking by
  frequency could only see "the variant uses fewer colours than the canonical"
  and dropped the *tail*; positional pairing sees exactly which colour has no
  counterpart, and can also catch one canonical colour mapping to two
  different variant colours — a real signal that the shape group is wrong,
  which is precisely the trap ADR-0154 §5 documents ("the vocabulary keys two
  visually different cells to one shape tuple").
- It buys the exactness with an assumption: that group members share a bitmap.
  That is what `shape_key` guarantees today. If ADR-0153's alias tolerance or
  any future grouping ever admits members whose bitmaps merely *resemble* each
  other, the per-offset pairing stops being evidence and the `ambiguous` path
  starts firing — loudly, on stderr, which is the intended failure mode rather
  than a silent permutation.
- No master palette table is added to the Python side, and none is needed. If
  one is ever wanted for another reason, this decision does not block it — it
  just does not depend on it.
- ADR-0154 §5's prose still reads "in NES colour-index order (0..3)". That
  remains the specification of the result; this ADR names the mechanism, and
  the two agree because same offset *is* same index.
