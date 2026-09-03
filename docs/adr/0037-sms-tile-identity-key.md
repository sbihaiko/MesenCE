# ADR-0037: SMS/GG tile-capture identity key (F2.1)

- Status: accepted
- Date: 2026-08-24
- Resolves the SMS half of ADR-0002 (key must be decided per console before
  the hires.txt 2xx spec freezes).

## Context
The hires-gbsms draft §3.2 originally proposed "CRAM base entry (0/16)" as the
whole palette key for SMS/GG mode 4. CRAM contents are rewritten constantly
(fades, palette swaps), so tile data + base half alone does not identify
appearance: a replacement captured during one CRAM state would render stale
colors later, violating the F2 1:1 criterion. The NES precedent keys on
palette *values*; the SMS analogue is the CRAM half the tile can address.

## Decision
An SMS/GG mode-4 tile is identified by
`{tile data, type, CRAM base, CRAM half snapshot}`:

- **Tile data**: 32 bytes 4bpp planar (mode 4), canonical unmirrored
  orientation (H/V mirroring are display attributes).
- **Type**: BG or OBJ (`TT`: `00`=BG, `01`=OBJ). BG tiles may address either
  CRAM half (nametable bit 11); sprites always address the upper half, so type
  and base are recorded separately.
- **CRAM base**: `00` (entries 0-15) or `10` (entries 16-31).
- **CRAM half snapshot**: the 16 raw CRAM entries of the addressed half at
  capture time — SMS: 16 bytes RGB222; GG: 16×RGB444 words, big-endian.
  Textual palette key: `TT` + `BB` + snapshot hex (SMS: 36 hex digits,
  GG: 68 hex digits).

Out of scope for the v1 key (builder refuses to record): SG-1000/ColecoVision
TMS9918 modes and SMS legacy modes 0-3 (draft §4 already excludes them);
SMS1-specific address-masking quirks (capture reads the canonical unmasked
tile address).

## Consequences
- Neutral 1:1 packs re-render pixel-identical by construction; CRAM animation
  produces one entry per palette variant (same trade-off as NES/GB, mitigated
  by `defaultTile`).
- The raw CRAM values (not resolved RGB) keep the key hardware-exact and let
  a loader re-resolve colors through its own video filter/color options.
- hires-gbsms draft §3.2 and the golden file are updated to this format.

## Alternatives
- Base entry only (draft's original text): stale-color replacements after any
  CRAM rewrite. Rejected.
- Only the CRAM entries actually referenced by the tile's pixels (zeroing
  unused ones): fewer spurious variants, but diverges from the NES precedent
  (full palette in key) and makes the key depend on decoding the tile data.
  Rejected for v1; can be revisited before the spec freezes.
