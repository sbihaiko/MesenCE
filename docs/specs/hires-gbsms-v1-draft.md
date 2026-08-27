# hires.txt extension for GB/SMS — v1-draft (proposal)

**Status:** **v1-draft / proposal — pending review by the HDNes/Mesen
community before any freeze** (ADR-0004). Nothing here is final; changes
based on feedback are draft revisions, not breaking changes. ·
**License for this spec:** CC0-1.0 ·
**Golden file:** [`golden/hires-gbsms/hires.txt`](golden/hires-gbsms/hires.txt) ·
**Validation:** `scripts/validate-specs.py`

The keywords MUST/SHOULD/MAY (RFC 2119) express the *intent of the
proposal*, conditioned on the draft status above.

## 1. Motivation

The HDNes `hires.txt` format (reference implementation: Mesen,
`Core/NES/HdPacks/`, current format version `<ver>109`) covers only the
NES PPU. GB and SMS are equally tile-based and have no HD pack standard;
OGG audio replacement for GB/SMS also has no standard (MSU-MD covers only
the Mega Drive). This proposal extends the existing format in a
**backward-compatible** way, using the `<ver>` field the format already
has, instead of creating a new format.

## 2. Compatibility strategy

1. The extension is signaled by `<ver>200` or higher (the 2xx range is
   reserved for non-NES systems; the 1xx line continues to belong to
   classic NES/HDNes).
2. A new mandatory `<system>` tag declares the target PPU. Old NES loaders
   already reject a `<ver>` above what they know — no old pack breaks, and
   no new pack is half-loaded by an old loader.
3. All existing tags keep their syntax and semantics
   (`<scale>`, `<img>`, `<tile>`, `<background>`, `<condition>`, `<bgm>`,
   `<sfx>`, `<options>`, `<overscan>`, `<patch>`, `<addition>`,
   `<fallback>`), reinterpreted only where the hardware differs (§3).

## 3. New / reinterpreted tags

### 3.1 `<system>` (new, MUST when `<ver>` ≥ 200)

```
<system>gb | gbc | sms | gg | sg1000 | coleco
```

### 3.2 `<tile>` — per-system tile key

The tile identity key (today: NES tile data + palette) becomes defined per
system. Decision recorded in ADR-0036 (GB/GBC) and ADR-0037 (SMS/GG): the
key always uses the palette **values** applied at capture time (never
indices/slots, which are dynamically reallocated by games), following the
precedent of the NES format — this is what guarantees 1:1 replacement.

| System | Tile data | Palette key (single hex field) |
|---|---|---|
| `gb` (DMG) | 16 bytes 2bpp | `TTPP` — TT: `00`=BG, `01`=OBJ; PP: value of the applied BGP/OBPx register |
| `gbc` | 16 bytes 2bpp | `TT` + 4×RGB555 big-endian of the applied CGB palette (18 hex) |
| `sms` | 32 bytes 4bpp (VDP mode 4) | `TT` + CRAM base (`00`/`10`) + snapshot of the 16 CRAM RGB222 entries (36 hex) |
| `gg` | 32 bytes 4bpp (VDP mode 4) | `TT` + CRAM base (`00`/`10`) + snapshot of the 16 CRAM RGB444 big-endian entries (68 hex) |
| `sg1000`/`coleco` | 8 bytes 1bpp (TMS9918) | foreground/background color pair of the pattern (draft; outside the builder's v1) |

Normative notes (MUST): VRAM bank (GBC) and H/V mirroring stay **outside**
the identity key — the bank only organizes the dumped PNG sheets, and
mirroring is a display attribute, as in NES. Tile data is recorded in the
canonical orientation (without mirrors).

Text format: the same comma-separated fields as the current format —
`<tile>png,dadosHex,chavePaletaHex,x,y,brilho,defaultTile` — with the tile
data in hex and the palette key as in the table.

### 3.3 `<background>` / `<condition>`

Kept. Conditions dependent on NES PPU addresses gain per-system equivalents
(e.g., `spriteNearby`, `memoryCheck` over the target system's bus). Draft:
the exact list of portable conditions will be finalized with the
community.

### 3.4 `<bgm>` / `<sfx>` (OGG audio for GB/SMS — the gap in PRD §4.1)

Syntax identical to the current one (`<bgm>id,arquivo.ogg[,loopPoint]`),
with the trigger defined per system: RAM/register address+value that
identifies the current track (the same `memoryCheck` mechanism as the
conditions). The host plays the OGG through its native mixer (OggMixer in
MesenCE), ducking the chip as it already does on NES.

## 4. Out of scope for this draft

- Non-tile modes (legacy SMS mode 0-3 beyond basic TMS9918).
- Normal/texture maps and shaders (SUPER ZSNES territory; see PRD §6).
- Any change to the existing NES pipeline.

## 5. Process

Public discussion (issue on the MesenCE fork + thread in the HDNes/Mesen
community) before freezing as `hires-gbsms-v1.md`. Experimental
implementations MUST treat `<ver>2xx` as unstable until the freeze.

## 6. Golden file

[`golden/hires-gbsms/hires.txt`](golden/hires-gbsms/hires.txt) — minimal
canonical example of a GB pack (syntactically validated by
`scripts/validate-specs.py`; semantics remain draft).
