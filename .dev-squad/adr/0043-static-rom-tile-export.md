# ADR-0043: Static ROM tile export as palette-agnostic `defaultTile` entries

- Status: accepted
- Date: 2026-08-25
- Complements F2 (HD Pack Builder) and feeds F5 (offline upscaling pipeline).

## Context
The HD Pack Builder records tiles *while playing*: a hires.txt key is
bitmap + palette (+ type), and the palette only exists at run time. Users
asked for reading the graphics straight from the ROM instead. The ROM holds
bitmaps, never palettes; and only NES CHR ROM stores them at a known place —
CHR RAM games, GB/GBC and SMS/GG copy or decompress tiles into VRAM by code.

## Decision
Add "Export ROM Tiles" to the HD Pack Builder (`EmulatorShortcut::
ExportRomTilesHdPack`, same `HdPackBuilderOptions` as recording):

- **NES** (`HdPackBuilder::AddRomTiles`): every 16-byte tile of CHR ROM is
  written as a `defaultTile` entry keyed by its absolute CHR index (CHR ROM
  keys are index-based in HDNes), drawn with a neutral gray ramp
  (`PaletteColors = 0F001030`, ignored by the loader for default tiles).
  CHR RAM games are refused with a message: recording is the only option.
- **GB/GBC/SMS/GG** (`HdTilePackBuilder::AddRomTiles`): heuristic scan of the
  ROM file in aligned 16-byte (2bpp) / 32-byte (4bpp planar) blocks; flat
  blocks are skipped; each block yields one BG and one OBJ `defaultTile`
  (wildcard key = type byte only, matching `HdTilePack::GetTile`), gray ramp,
  PNG sheet grouped by 16 KB ROM bank. Compressed graphics are invisible to
  the scan: coverage is partial by design and the UI says so.
- Export merges into an existing pack (both builders already load the
  folder's pack first) and re-recording merges on top of an export, keeping
  the `defaultTile` entries; recorded palette variants are added alongside
  and win over the default at load time (exact key beats wildcard).

## Consequences
- 100% bitmap coverage for NES CHR ROM games without playing; the artist
  paints once per bitmap and loses per-palette variants unless they also
  record. The export is *not* 1:1 with the original rendering (gray art).
- GB/SMS export catches uncompressed tiles only (e.g. 12 of 26 on-screen
  tiles of the F1 test ROM are runtime-generated and not found).
- The neutral gray sheets are the natural input for the F5 upscaling
  pipeline.

## Alternatives
- Emulate to fill VRAM then dump VRAM: still needs gameplay/time and misses
  unused banks. Rejected as the *static* option (recording covers it).
- Decompress known compression schemes per game: out of scope; recording
  fills those gaps.
