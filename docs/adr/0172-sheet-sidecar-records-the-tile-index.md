# ADR-0172: A sheet sidecar records each tile's CHR index, so a rebuilt pack still matches on a CHR ROM game

- Status: accepted (2026-09-12, at the user's request after the measurement
  below; implemented the same day across `Core/`, `scripts/mep_build.py` and
  the sheet sidecar format)
- Date: 2026-09-12
- Related: ADR-0153 (artist-legible sheets — the sidecar this amends),
  ADR-0043 (CHR ROM keys are index-based in HDNes), ADR-0005 (MEP textures
  as an envelope over `hires.txt`), issue #170
- Supersedes / amends: ADR-0153, the sidecar `cells[].tiles[]` record —
  a tile entry gains an optional `index`

## Context

A `hires.txt` key is not one thing. `HdPackTileInfo::ToString`
(`Core/NES/HdPacks/HdData.h`) writes two forms, and
`HdNesPack::GetMatchingTile` looks up whichever the game calls for:

- CHR RAM game — `<tile>img,<32 hex of tile data>,palette,x,y,brightness,default`
- CHR ROM game — `<tile>img,<tile index>,palette,x,y,brightness,default`

The bootstrap gets this right: on Mega Man 3 (CHR ROM) it writes short keys
and the emulator reports a 100 % background tile match rate. The ADR-0153
sheet sidecars, however, describe a cell's tiles as
`{"tile": "<32 hex>", "palette": "<8 hex>"}` — bitmap data only, no index,
because `SheetTileKey` (`Core/NES/HdPacks/TileSheetTypes.h`) carries
`TileData` + `PaletteColors` and nothing else. So when `mep_build.py build`
regenerates `hires.txt` from the sheets, it emits the CHR RAM form for every
key of a CHR ROM game.

Measured on a freshly recorded Mega Man 3 pack, over a 100 s headless run,
with nothing changed between the runs but the rebuild
(`[HDPack-Debug] bg tile match rate`, on the frames where the sheets carry
the scene at all):

| Pack | matched |
|---|---|
| as the bootstrap wrote it | 100 % — its ADR-0043 `defaultTile` export covers every CHR tile |
| after `mep_build.py build`, before this ADR | **0** of 3 455 861, 3 390 239 and 3 192 008 |
| after `mep_build.py build`, with this ADR | 479 861, 295 199 and 450 368 of the same three |

Zero is the number that matters: not one tile the sheets do carry was
reaching the screen. (The rebuilt pack matches a fraction of the frame by
design — ADR-0160 has it point at `sheets/` alone, and the scenes a captured
screen owns leave the sheets entirely under ADR-0156. Those frames report
0 % in both columns and are not counted above.)

The failure is silent and looks like nothing at all: the pack still loads, so
its `<background>` captures (ADR-0050) keep drawing, and the scene renders at
4x with the original tile art. An artist repaints a sheet, rebuilds, sees the
game exactly as before and has nothing to go on — which is how this reached
the F9.18 panel as "painted sheets have no effect".

Non-goals: changing how a CHR RAM pack is keyed (it already round-trips);
making `mep_build` infer an index from pixels (a reconstruction that only
works while a pack still carries `chr/`, and a second source of truth for the
same key); any change to `hires.txt` semantics, which stay HD Pack's
(ADR-0005).

## Decision

**The sidecar carries the index, because the Core knows it at write time.**

1. `SheetTileKey` gains `TileIndex` (int32, `-1` when unknown). It is *not*
   part of the key's identity: `operator==`, `operator<` and the hash keep
   comparing `TileData` + `PaletteColors` only, so vocabulary building, dedup
   and every existing grouping decision are bit-for-bit unchanged. The
   recorder fills it from `HdTileKey::TileIndex` and leaves it `-1` on a CHR
   RAM tile, where the field means nothing.

   No bank id travels with it: `HdBuilderPpu` already computes a CHR ROM
   tile's index as `AbsoluteTileAddr / 16`, so the value is absolute across
   the whole CHR ROM and is exactly what `HdPackTileInfo::ToString` prints.

2. A sidecar tile entry gains one optional field, written only when the index
   is known:

   ```json
   { "tile": "00FD010100EF080800FD010100EF0808",
     "palette": "0F0F0F0F",
     "index": 155 }
   ```

   A sidecar without it is valid and means "CHR RAM game, or a pack recorded
   before this ADR" — readers must not require it.

3. `mep_build.py build` emits the index form for a tile when **both** hold:
   the key source's own `<tile>` lines are index-keyed (that is what says
   "this game is CHR ROM"), and the sidecar entry carries an `index`. Any
   other combination emits the data form, exactly as today. A CHR ROM pack
   whose sidecars predate this ADR therefore still rebuilds — and still
   mismatches at run time, which the build now says out loud rather than
   leaving to be discovered in-game:

   ```
   error: metatiles: 24 crop(s) carry no tile index, but this game's keys are
   index-based (CHR ROM) — the rebuilt pack would match nothing at run time;
   re-record the pack with a build that has ADR-0172
   ```

   It is an error, not a warning: a 0 %-match pack is not a degraded pack,
   it is a pack that does nothing.

4. The index is the absolute CHR index HDNes keys by (ADR-0043), the same
   value `HdPackTileInfo::TileIndex` holds — not a per-sheet or per-bank
   ordinal.

## Consequences

- **Packs recorded before this ADR do not become valid.** Their sidecars have
  no index; on a CHR ROM game the rebuild now fails with the message above
  instead of producing a pack that renders nothing. Re-recording is the fix,
  and it is cheap (a bootstrap run). CHR RAM packs are unaffected either way.
- The sidecar grows by one small number per tile entry. `adjacency.json` and
  the `sheets/*.json` of a large pack grow a couple of percent.
- Every reader of `cells[].tiles[]` — `mep_build`, `compose_engine`,
  `mep_lint`, `sheet_repaint` — must treat the new fields as optional. The
  composition editor does not use them: it composes by node, and the keys
  travel with the cell record it copies.
- A future exporter that wants to *verify* a key, rather than copy it, now
  has the datum to do so without the ROM.
- The `[HDPack-Debug] bg tile match rate` line stays the ground truth for
  "did this pack actually apply", and is what any regression test for this
  should read.
