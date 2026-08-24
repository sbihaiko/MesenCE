# ADR-0036: GB/GBC tile-capture identity key (F2.1)

- Status: accepted
- Date: 2026-08-24
- Resolves the GB half of ADR-0002 (key must be decided per console before the
  hires.txt 2xx spec freezes).

## Context
The NES builder keys tiles on `{tile bytes, palette RAM values}` (CHR-RAM path)
— the palette *values*, not the palette *slot*, so a tile drawn with different
colors becomes a distinct entry and replacement is always 1:1 faithful. GB VRAM
is always RAM (tiles are copied from ROM at runtime), so the analogous path is
the NES CHR-RAM one: there is no stable ROM tile index to key on. The
hires-gbsms draft §3.2 originally proposed "CGB palette index (0-7)" as the CGB
palette key, but games reload palette slots constantly (fades, scene changes):
the same index does not identify the same appearance, which breaks the F2
success criterion (reinstalled neutral pack renders identical to the original).

## Decision
A GB tile is identified by `{tile data, type, applied palette}`:

- **DMG (`gb`)**: 16 bytes 2bpp + type (BG/OBJ) + the applied palette register
  *value* (BGP for BG, OBP0/OBP1 for OBJ — the value, not which register).
  Textual palette key: 4 hex digits `TTPP` (TT: `00`=BG, `01`=OBJ; PP: register
  value). The 4 configurable DMG shade colors are display configuration, not
  identity.
- **CGB (`gbc`)**: 16 bytes 2bpp + type (BG/OBJ) + the 4 RGB555 colors of the
  CGB palette at capture time. Textual palette key: 18 hex digits
  `TT` + 4×RGB555 big-endian. The palette *index* (0-7) is NOT part of the key.
- **VRAM bank (0/1) is NOT part of the identity key**: the tile bytes are
  already in the key, so identical data in different banks is the same visual
  tile. The bank is used only to organize the dumped PNG sheets.
- H/V mirroring and BG priority are display attributes, not identity (same as
  NES).

## Consequences
- Pack authors key replacements on appearance, and a neutral 1:1 pack
  re-renders pixel-identical by construction.
- Palette animation (fades) produces one entry per palette variant — the same
  known trade-off the NES HDNes format has, mitigated by the existing
  `defaultTile` mechanism (match any palette).
- hires-gbsms draft §3.2 and the golden file are updated to this format; the
  draft stays a draft (ADR-0004) but the key format is now the recorded
  reference for the eventual freeze.

## Alternatives
- CGB palette index (draft's original text): unstable across scenes; a pack
  authored against it renders wrong colors after any palette reload. Rejected.
- Include VRAM bank in the key: creates spurious duplicate entries for
  identical tiles; adds nothing (data already in key). Rejected.
