"""ADR-0196: the `<addition>` tag, its synthetic target key, and the checks
that make that key provably unmatched by the ROM.

Everything here is a pure decision over strings and ints — no pack, no ROM
load, no emulator — so `mep_build.py` (which serializes), `mep_lint.py` (which
gates) and `compose_engine.py` (which authors) all read the *same* rule
instead of three copies of it drifting apart.

The tag itself (`HdPackLoader::ProcessAdditionTag`, HD Pack version 107+):

    <addition>origTileData,origPalette,offsetX,offsetY,addTileData,addPalette[,ignorePalette]

`HdNesPack::ProcessAdditionalSprites` draws the *additional* tile's HD art at
`(offsetX, offsetY)` from every on-screen match of the *original* tile. The
game never draws the additional tile, so its key is synthetic by construction
— and a synthetic key that collided with a real one would paint the artist's
overflow onto an unrelated tile. ADR-0196 §3 is how that is ruled out, once
per console key kind:

* **CHR ROM.** The target index is `chrTileCount + n`. An index past the end
  of CHR can never be fetched, so it can never collide. `chr_rom_target`
  computes it and `chr_rom_unmatched` is the assertion, against the ROM's own
  iNES header (`chr_tile_count`).
* **CHR RAM.** A key reserved by convention on *both* halves, because
  `HdTileKey::operator==` compares the palette and the 16 pattern bytes
  together on CHR RAM: the pattern is all-zero but for one marker row carrying
  `n`, and the palette is the four entries `$0D` — the "blacker than black"
  index no shipping game writes to a palette. The check ADR-0196 §3 mandates
  is on the **palette** (`reserved_palette_evidence`): the pattern half alone
  would inherit the recording-coverage gap without the palette's protection,
  and the result is reported as *evidence-bounded, not proven*.

`n` is **1-based on purpose**. The 0th reserved pattern would be sixteen zero
bytes, which is one of the most-recorded tiles there is (a blank sprite cell);
starting at 1 keeps the pattern half non-degenerate even before the palette
half is considered.
"""

import sys
from pathlib import Path

# ADR-0196 §3: `$0D` in all four entries. `0x0D` is "blacker than black" — a
# level below the NES's black that no shipping game writes to a palette, and
# that Mesen's own palette renders as a distinct entry, so a recording that
# ever showed it would be visible rather than silent.
RESERVED_PALETTE = "0D0D0D0D"

# The marker row of the reserved pattern: row 7 of the tile, i.e. byte 7 of
# bit-plane 0 and byte 15 of bit-plane 1. Two bytes, so 65 535 synthetic cells
# fit in one pack — far past any plausible overflow layer, and a fixed row
# keeps the pattern recognisable by inspection.
MARKER_LOW = 7
MARKER_HIGH = 15
MAX_ORDINAL = 0xFFFF

# The tag's own limits, from HdPackLoader::ProcessAdditionTag.
MIN_VERSION = 107
IGNORE_PALETTE_VERSION = 108
MIN_FIELDS = 6
MAX_FIELDS = 7


class AdditionError(Exception):
    """A synthetic target, anchor or offset that ADR-0196 refuses."""


def index_token(index: int) -> str:
    """A CHR index as `hires.txt` writes it — the shortest even number of hex
    digits that holds it, matching `HexUtilities::ToHex`. Kept here rather
    than in `mep_build` so the build and the lint format an index the same
    way; `mep_build._index_token` delegates to it."""
    v = int(index)
    for digits in (2, 4, 6):
        if v < (1 << (4 * digits)):
            return f"{v:0{digits}X}"
    return f"{v:08X}"


def is_index_key(token: str) -> bool:
    """True when a `<tile>`/`<addition>` key token is a CHR index rather than
    32 hex digits of pattern data — the loader's own cutoff
    (`HdPackLoader::ReadTileData`: 32 characters or more is CHR RAM)."""
    return len(str(token).strip()) < 32


# -- the CHR RAM half ---------------------------------------------------------

def chr_ram_target(ordinal: int) -> str:
    """The 32-hex pattern of the `ordinal`-th synthetic cell (1-based)."""
    n = int(ordinal)
    if not 1 <= n <= MAX_ORDINAL:
        raise AdditionError(
            f"synthetic ordinal {n} is outside 1..{MAX_ORDINAL} (ADR-0196 §3)")
    data = bytearray(16)
    data[MARKER_LOW] = n & 0xFF
    data[MARKER_HIGH] = (n >> 8) & 0xFF
    return data.hex().upper()


def chr_ram_ordinal(tile_data: str):
    """`n` when `tile_data` is the reserved pattern, else None. The inverse of
    `chr_ram_target`, and the only way a reader tells a synthetic CHR RAM key
    from a recorded one by looking at the key alone."""
    text = str(tile_data).strip().upper()
    if len(text) != 32:
        return None
    try:
        data = bytes.fromhex(text)
    except ValueError:
        return None
    for i, byte in enumerate(data):
        if byte and i not in (MARKER_LOW, MARKER_HIGH):
            return None
    n = data[MARKER_LOW] | (data[MARKER_HIGH] << 8)
    return n if n >= 1 else None


def reserved_palette_evidence(palettes) -> list:
    """Every observed palette equal to the reserved one, uppercased and
    deduplicated. ADR-0196 §3's evidence check: the build runs it over the
    keys the recording actually produced and refuses a CHR RAM synthetic
    target when it is non-empty. An empty result is *evidence-bounded*, not a
    proof — the recordings cover routes, not the game."""
    return sorted({str(p).strip().upper() for p in palettes
                   if str(p).strip().upper() == RESERVED_PALETTE})


# -- the CHR ROM half ---------------------------------------------------------

def chr_tile_count(rom: Path) -> int:
    """8x8 tiles in the ROM's CHR ROM, from the iNES header (byte 5 counts
    8 KB units, the NES 2.0 MSB nibble is the high 4 bits of that count).
    0 means the game has no CHR ROM at all, i.e. it is a CHR RAM game."""
    data = Path(rom).read_bytes()
    if len(data) < 16 or data[0:4] != b"NES\x1a":
        raise AdditionError(f"{rom}: not an iNES image")
    units = data[5]
    if (data[7] & 0x0C) == 0x08:
        units |= (data[9] & 0xF0) << 4
    return units * 8192 // 16


def chr_rom_target(tile_count: int, ordinal: int) -> int:
    """The CHR index of the `ordinal`-th synthetic cell (1-based), i.e. the
    first index past the end of CHR, plus the ones already taken."""
    n = int(ordinal)
    if not 1 <= n <= MAX_ORDINAL:
        raise AdditionError(
            f"synthetic ordinal {n} is outside 1..{MAX_ORDINAL} (ADR-0196 §3)")
    if int(tile_count) <= 0:
        raise AdditionError(
            "a CHR ROM synthetic target needs the ROM's CHR tile count "
            "(ADR-0196 §3); this ROM reports none")
    return int(tile_count) + n - 1


def chr_rom_unmatched(index: int, tile_count: int) -> bool:
    """ADR-0196 §3's CHR ROM assertion: the index is past the end of CHR, so
    the PPU can never fetch it."""
    return int(index) >= int(tile_count) > 0


# -- the tag ------------------------------------------------------------------

def addition_line(anchor_key, offset, target_key) -> str:
    """One `<addition>` line. `anchor_key`/`target_key` are `(tileData,
    palette)` as `hires.txt` spells them; `offset` is `(dx, dy)` in **native
    pixels**, relative to the anchor cell's own top-left pixel — which is what
    `HdNesPack::InsertAdditionalSprite` adds to the matched pixel's
    coordinates. `ignorePalette` is never written: ADR-0196 §3 keeps the
    palette half of the synthetic key load-bearing."""
    data, pal = (str(x).strip().upper() for x in anchor_key)
    tdata, tpal = (str(x).strip().upper() for x in target_key)
    dx, dy = int(offset[0]), int(offset[1])
    return f"<addition>{data},{pal},{dx},{dy},{tdata},{tpal}"


def parse_addition(params: str):
    """`(anchor, offset, target, ignore_palette)` from an `<addition>` line's
    parameter text, or raise `AdditionError`. `anchor`/`target` are
    `(tileData, palette)` uppercased; `ignore_palette` is None when the field
    is absent."""
    fields = [f.strip() for f in str(params).split(",")]
    if not MIN_FIELDS <= len(fields) <= MAX_FIELDS:
        raise AdditionError(
            f"addition takes {MIN_FIELDS} or {MAX_FIELDS} fields, not {len(fields)}")
    try:
        dx, dy = int(fields[2]), int(fields[3])
    except ValueError:
        raise AdditionError(f"addition offset is not a pair of integers: {fields[2]},{fields[3]}")
    ignore = None
    if len(fields) == MAX_FIELDS:
        ignore = fields[6].strip().upper() in ("Y", "YES", "TRUE", "1")
    return ((fields[0].upper(), fields[1].upper()), (dx, dy),
            (fields[4].upper(), fields[5].upper()), ignore)


def plan_sheet_additions(sheet_docs, index_keyed: bool, tile_count: int = 0):
    """`(lines, synthetic_keys, errors)` for every sheet that authored an
    ADR-0196 overflow layer.

    `sheet_docs` are `mep_build.SheetDoc`s: each `additions[]` record names a
    pose, the anchor key, the measured offset and the sheet cell that carries
    the synthetic target. The cell is the single source of the target key — the
    record never restates it, so the `<tile>` rule the sheet emits and the
    `<addition>` that points at it cannot drift apart.

    `tile_count` is the ROM's CHR tile count, and 0 means "no ROM was given".
    On a CHR ROM pack that is itself an error: ADR-0196 §3's proof *is* the
    header assertion, and a build with no ROM cannot make it."""
    lines, keys, errors = [], set(), []
    for sd in sheet_docs:
        by_index = {c.get("index"): c for c in sd.cells if isinstance(c, dict)}
        for rec in sd.additions:
            if not isinstance(rec, dict):
                errors.append(f"{sd.name}: an additions[] entry is not an object")
                continue
            where = f"{sd.name} addition {rec.get('pose') or '?'}"
            anchor = rec.get("anchor") if isinstance(rec.get("anchor"), dict) else {}
            cell = by_index.get(rec.get("cell"))
            if cell is None:
                errors.append(f"{where}: cell {rec.get('cell')!r} is not on this sheet")
                continue
            if not cell.get("synthetic"):
                errors.append(f"{where}: cell {rec.get('cell')} is not marked synthetic "
                              "in the sidecar (ADR-0196 §4)")
                continue
            tiles = cell.get("tiles") or []
            entry = tiles[0] if tiles and isinstance(tiles[0], dict) else None
            if entry is None:
                errors.append(f"{where}: synthetic cell {rec.get('cell')} carries no tile key")
                continue
            try:
                dx, dy = int(rec.get("offsetX")), int(rec.get("offsetY"))
            except (TypeError, ValueError):
                errors.append(f"{where}: offsetX/offsetY are not whole pixels")
                continue
            a_key = _key_of(anchor, index_keyed)
            t_key = _key_of(entry, index_keyed)
            if a_key is None or t_key is None:
                errors.append(f"{where}: anchor or target key is malformed")
                continue
            if index_keyed:
                index = int(t_key[0], 16)
                if not tile_count:
                    errors.append(
                        f"{where}: this pack keys by CHR index, so ADR-0196 §3's proof is "
                        "an assertion against the ROM's iNES header — re-run `build` with "
                        "--rom <the ROM this pack was recorded from>")
                    continue
                if not chr_rom_unmatched(index, tile_count):
                    errors.append(
                        f"{where}: target index {t_key[0]} is inside the ROM's CHR "
                        f"({tile_count} tiles), so the game can draw it (ADR-0196 §3)")
                    continue
            else:
                why = target_verdict(t_key, False)
                if why:
                    errors.append(f"{where}: {why}")
                    continue
            lines.append(addition_line(a_key, (dx, dy), t_key))
            keys.add(t_key)
    return lines, keys, errors


def emit_additions(rom, sheet_docs, index_keyed: bool, out_lines: list, body: list):
    """Serialize the overflow layer into `out_lines` and return
    `(body, synthetic_keys, rc)`.

    `body` comes back with every carried `<addition>` removed once the sheets
    author one: the sheets are the source of truth for the layer, and
    re-emitting a carried copy beside a generated one would duplicate the tag
    on every rebuild. `rc` is 2 when ADR-0196 refused something, and the
    reasons are already on stderr — the caller returns it unchanged.

    Lives here rather than in `mep_build.cmd_build` so the whole ADR reads in
    one file, and so the build's per-file line ceiling does not have to move
    for a feature whose decisions are all in this module anyway."""
    tile_count = 0
    if rom:
        try:
            tile_count = chr_tile_count(Path(rom))
        except (OSError, AdditionError) as e:
            print(f"error: {e}", file=sys.stderr)
            return body, set(), 2
    lines, keys, errors = plan_sheet_additions(sheet_docs, index_keyed, tile_count)
    if errors:
        for msg in errors:
            print(f"error: {msg}", file=sys.stderr)
        return body, keys, 2
    if lines:
        body = [b for b in body if not b.startswith("<addition>")]
        out_lines.extend(lines)
        print(f"info: {len(lines)} <addition> line(s) from the sheets' overflow layer, "
              f"{len(keys)} synthetic target key(s) — the only keys this toolchain "
              "emits that no recording observed (ADR-0196 §3)")
    return body, keys, 0


def _key_of(entry: dict, index_keyed: bool):
    """`(tileData, palette)` as `hires.txt` spells this sidecar tile record —
    the CHR index on an index-keyed pack, the 32-hex pattern otherwise."""
    pal = str(entry.get("palette") or "").strip().upper()
    if len(pal) != 8:
        return None
    if index_keyed:
        idx = entry.get("index")
        if not isinstance(idx, int) or idx < 0:
            return None
        return (index_token(idx), pal)
    data = str(entry.get("source") or entry.get("tile") or "").strip().upper()
    return (data, pal) if len(data) == 32 else None


def target_verdict(target, index_keyed: bool, max_real_index: int = -1):
    """None when the target key satisfies ADR-0196 §3 for the pack's key kind,
    else the reason it does not.

    `index_keyed` is the pack's own key form (a CHR ROM pack keys by index).
    `max_real_index` is the largest index any **non-synthetic** `<tile>` rule
    of the pack uses: a linter has no ROM, so the pack-local form of §3's
    header assertion is "past every index this game's own manifest names".
    The build does the header assertion itself, with the ROM in hand."""
    data, pal = (str(x).strip().upper() for x in target)
    if index_keyed:
        if not is_index_key(data):
            return ("a CHR ROM pack's addition target must be keyed by CHR index, "
                    f"not by 32 hex digits of pattern data: {data}")
        try:
            index = int(data, 16)
        except ValueError:
            return f"addition target index is not hexadecimal: {data}"
        if max_real_index >= 0 and index <= max_real_index:
            return (f"addition target index {data} is not past the pack's own CHR "
                    f"({index_token(max_real_index)} is keyed by a <tile> rule), so it is "
                    "not provably unmatched (ADR-0196 §3)")
        return None
    if is_index_key(data):
        return ("a CHR RAM pack's addition target must carry 32 hex digits of pattern "
                f"data, not a CHR index: {data}")
    if pal != RESERVED_PALETTE:
        return (f"addition target palette {pal} is not the reserved {RESERVED_PALETTE} "
                "(ADR-0196 §3 reserves both halves of a CHR RAM key)")
    if chr_ram_ordinal(data) is None:
        return (f"addition target pattern {data} is not the reserved pattern — all bytes "
                f"zero but {MARKER_LOW} and {MARKER_HIGH}, carrying a non-zero ordinal "
                "(ADR-0196 §3)")
    return None
