# ADR-0178: A sheet sidecar records the unflipped tile data, so a repainted sprite cell still matches on a CHR RAM game

- Status: accepted (2026-09-12, at the user's request after the measurement
  below; implemented the same day across `Core/`, `scripts/mep_build.py` and
  the sheet sidecar format)
- Date: 2026-09-12
- Related: ADR-0172 (the same defect's CHR ROM half — the sidecar gained
  `index` there and gains `source` here), ADR-0153 (artist-legible sheets —
  the sidecar this amends), ADR-0043 (CHR ROM keys are index-based),
  ADR-0005 (MEP textures as an envelope over `hires.txt`), issue #181
- Supersedes / amends: ADR-0153, the sidecar `cells[].tiles[]` record —
  a tile entry gains an optional `source` and `mirror`

## Context

The recorder bakes a sprite's OAM flip bits into the shape it records.
`HdBuilderPpu::CaptureOam` copies the CHR tile and then calls `ApplyFlips`
before `RecordSprite`, and the reason is a good one, stated in its own
comment: the two mirrored halves of a figure share their CHR, and baking the
flip is what lets them sit side by side on a sheet instead of collapsing into
one cell — a group cannot place the same vocabulary entry twice.

The run time does not key by that shape. `HdNesPpu` fills
`HdPpuTileInfo::TileData` from the raw, unflipped CHR and carries
`HorizontalMirroring`/`VerticalMirroring` as separate fields; `HdNesPack::DrawTile`
mirrors the *replacement art* when it draws. One `hires.txt` key therefore
serves both directions, and the flipped bitmap is a key nothing ever looks up.

On a CHR ROM game this is invisible: the key is the CHR index (ADR-0043), and
a flip is an attribute bit that does not touch the index. On a CHR RAM game
the key **is** the 32 hex of tile data, so every flipped sprite cell on a
sheet carries a key that does not exist in the pack's own manifest.

Measured over the four golden packs of 2026-09-12, counting sprite-sheet tile
entries whose `(key, palette)` has no `<tile>` line in the pack's own
`hires.txt`, and re-testing the misses with the bitmap un-flipped:

| pack | key form | sprite tile entries | no matching key | recovered by un-flipping |
|---|---|---|---|---|
| Contra (1988) | data (CHR RAM) | 446 | **156 (34 %)** | 155 (99 %) — H 83, V 5, H+V 67 |
| Zelda 1 | data (CHR RAM) | 240 | **88 (36 %)** | 88 (100 %) — H 56, V 16, H+V 16 |
| Mega Man 3 | index (CHR ROM) | 451 | 2 (0 %) | — |
| Excitebike | index (CHR ROM) | 383 | 2 (0 %) | — |

The recovery rate is what makes this a diagnosis rather than a correlation:
the gap *is* the flip, not a stray class of tiles the sheets happen to hold.

The failure has the same silent shape ADR-0172 described. The pack loads, its
`<background>` captures keep drawing, and a third of the sprite cells an
artist is invited to paint are inert — while the twin cell they mirror, which
the artist had no reason to paint, would have covered both directions.

Non-goals: changing how the flip is baked (the layout reason stands, and the
sheet stays the artist's map of the figure); making `mep_build` un-flip a key
it finds unmatched (the same reconstruction ADR-0172 refused — a second
source of truth for the same key); anything at run time, which is already
correct and is what this ADR trusts.

## Decision

**The sidecar carries the key the run time looks up, because the recorder
knows it at bake time.** ADR-0172 did this for the CHR ROM half with `index`;
this is the CHR RAM half.

1. `MesenSheets::ApplyTileFlips(uint8_t* tileData, bool h, bool v)` moves into
   `TileSheetTypes.h` (host-free, unit-testable) and `HdBuilderPpu::ApplyFlips`
   becomes a call to it. One implementation, so the un-bake below cannot drift
   from the bake. Per axis the transform is an involution: applying the same
   flags twice restores the original bytes.

2. `HdBuilderPpu::CaptureOam` sets `sprite.HorizontalMirroring` and
   `sprite.VerticalMirroring` from the OAM attribute bits before it calls
   `RecordSprite`. The bake is unchanged; the flags are now *also* recorded
   instead of being consumed and discarded.

3. `SheetTileKey` gains `SourceTileData[16]` and `Mirrors` (bit 0 = horizontal,
   bit 1 = vertical). Like ADR-0172's `TileIndex` they are **outside the key's
   identity**: `operator==`, `operator<` and the hash keep comparing
   `TileData` + `PaletteColors` only, so the vocabulary, the dedup, the
   grouping, the poses and every sheet layout are bit-for-bit unchanged.
   `HdPackBuilder::ShapeIdFor` fills them by un-baking the flags off the
   recorded bitmap.

4. A sidecar tile entry gains two optional fields, written only when the shape
   was flipped (`Mirrors != 0`):

   ```json
   { "tile": "0030397B423C00000030397B423C0000",
     "palette": "FF0F3037",
     "source": "000C9CDE423C0000000C9CDE423C0000",
     "mirror": "H" }
   ```

   `mirror` is `"H"`, `"V"` or `"HV"`. An entry without them means *this shape
   was not flipped, or the pack was recorded before this ADR* — readers must
   not require them, exactly as with `index`.

5. `mep_build.py build` emits `source` in place of `tile` when the game's keys
   are data-based (that is, not index-keyed — the same test ADR-0172 §3 uses
   to decide the other direction) and the entry carries one. Index-keyed packs
   are untouched: the index already serves both directions.

6. A pack recorded before this ADR is **detected, not repaired**. When a
   data-keyed pack has crops whose key is absent from the key source while an
   un-flip of that key is present, the build fails:

   ```
   error: spr014.png: 12 crop(s) carry a flip-baked tile key the run time never
   looks up, and the unflipped twin is in this game's key source — repainting
   them would do nothing; re-record the pack with a build that has ADR-0178
   ```

   It is an error for ADR-0172's reason: a cell that cannot match is not a
   degraded cell, it is a cell that does nothing. The un-flip here is used only
   to *recognise* the condition, never to emit a key from it.

7. Two sheet cells may now emit the same key: a mirrored cell and the twin it
   mirrors. The existing per-sheet collision rule decides, unchanged — a
   painted crop beats an untouched one, and the `repeat` count is logged. The
   sheet keeps both cells: they are the artist's map of the figure, and
   collapsing them would undo the reason the flip is baked at all.

## Consequences

- **Packs recorded before this ADR do not become valid on a CHR RAM game.**
  Their sidecars have no `source`; the rebuild now fails with the message
  above instead of producing sprite cells that render nothing. Re-recording is
  the fix and is cheap (a bootstrap run). CHR ROM packs are unaffected in both
  directions, as the table shows.
- **An artist can no longer paint a cell and its mirror differently.** They
  resolve to one key, and the run time mirrors whichever art wins. This is not
  a regression — it was always true at run time; the sheets merely implied
  otherwise. The collision is now visible in the build log rather than being
  discovered as "half my repaint disappeared".
- A shape whose flipped bitmap happens to equal another CHR tile's unflipped
  bitmap is keyed by whichever sighting the recorder interned first. Both keys
  are real tiles of the game, so both render; which of the two a sheet cell
  names is arbitrary. Measured zero times across the four golden packs, and
  not worth a rule.
- The sidecar grows by two small fields, and only on flipped entries — a third
  of sprite tile entries on the measured CHR RAM packs, none on CHR ROM.
- Every reader of `cells[].tiles[]` — `mep_build`, `compose_engine`,
  `mep_lint`, `sheet_repaint` — must keep treating the new fields as optional.
  The composition editor does not use them: it composes by node.
- The two crops each of Mega Man 3 and Excitebike that still match nothing are
  not explained by this ADR and are not a flip. They are left open.
- The `[HDPack-Debug] bg tile match rate` line stays the ground truth for "did
  this pack actually apply". It reports *background* tiles, so it will not move
  when this lands — the regression test for this ADR is the key-coverage count
  in the table above, not the log line.
