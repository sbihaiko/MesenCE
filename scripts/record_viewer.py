"""The live recording viewer (ADR-0169) — watches a live recording as it runs
and draws the two things the recorder publishes: the composed frame and a
reconstruction of that same frame from the layers the PPU rendered, read as
data.

Two recorders share one wire format (Utilities/LiveRecordFormat.h):

    scripts/headless_record  a scripted run launched from a terminal, which
                             publishes into <prefix>-live/ every <ms> of wall
                             clock as an atomic file swap (lossy-latest,
                             ADR-0169 section 1)
    the emulator itself      a human playing with a real controller, while the
                             interactive LiveFrameRecorder publishes the same
                             files into the convention slot
                             <HomeFolder>/LiveRecording (the emulator's Tools
                             menu toggles it; there is no target frame)

The files in either directory are:

    frame.ppm        the composed frame the emulator rendered (P6, its own scale)
    sprites.json     the sprite layer as data: raw OAM, palette RAM, PPU control
    chr.bin          the $0000-$1FFF pattern tables, mapper-resolved
    background.json  the background layer's scroll/control bits + which nametable
                     page the PPU would fetch (loopy "t" + fine X; 2026-09-08
                     ADR-0169 "capture every layer" update)
    nametables.bin   the background's $2000-$2FFF tile+attribute bytes, mapper-
                     resolved (written alongside sprites.json like chr.bin is)
    palette.json     the 64 RGB colors this run renders with (written once)
    status.json      progress / done, and which ROM the frames are of

By convention this tool attaches to the emulator's own slot, so there is
nothing to type to watch a live session:

    python3 scripts/record_viewer.py

Pass a path to watch a headless run instead (or type one in the Live dir box
and click Attach):

    python3 scripts/record_viewer.py runs/<rom>-<stamp>-live/

Either way this tool only polls the directory and draws what it finds; it never
writes a byte into it, and it never launches a recording — start and stop live
recording from the emulator, start headless runs from a terminal.

The right (or lower, when the panes stack) pane is a *reconstruction* of the
frame, not a second capture: OAM
entries are expanded through the NES 8x8/8x16 rules of NesPpu::LoadSprite and
the background tiles are re-laid out through the captured loopy scroll, then
both are multiplexed the way the 2C02's priority logic does (front sprites over
everything; behind-background sprites only through a backdrop pixel). So it
applies what a single end-of-frame capture can prove — palette RAM, OAM, pattern
tables, nametables, scroll, the mask bits — and ignores what it cannot see:
the 8-sprites-per-scanline limit and any mid-frame scroll split. Recordings from
before the background capture land on the wire format show only sprites over the
backdrop color, the way this tool always did. The pane may still disagree with
the composite in those spots; the layer checkboxes under it exist to hide a
layer and see what the others would look like on their own.

The window itself is laid out by record_viewer_layout.py — pane orientation,
the shared zoom and every caption string live there, host-free and unit tested
(scripts/test_record_viewer_layout.py), so the tkinter class below is only
widgets plus the draw calls.

stdlib plus tkinter, an external tool in `scripts/` never linked into the
emulator (ADR-0165). The pure reconstruction helpers live above the GUI class
so they can be exercised without a display.
"""

import argparse
import json
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, ttk

import record_viewer_layout as vl

# The NES sprite plane, in its own native pixels (the recorder's frame.ppm may
# be scaled, e.g. 2x -> 512x480; geometry_scale() recovers the factor).
NATIVE_W = 256
NATIVE_H = 240

# An OAM y >= 0xF0 puts the sprite's rows entirely below the last visible
# scanline (it wrapped off the bottom), so the PPU never shows it — skip it
# the same way the hardware does.
HIDDEN_SPRITE_Y = 0xF0


def emulator_live_dir():
    """The convention slot the emulator's own live recorder publishes to
    (UI/Config/ConfigManager.cs: LiveRecordingFolder). Mirrors the C# rule for a
    non-portable install: HomeFolder = <MyDocuments on Windows, ApplicationData
    elsewhere>/MesenCE, then LiveRecording/ under it. A portable emulator (a
    settings.json beside the executable) uses that folder instead; point this
    tool at it explicitly in that case."""
    base = Path.home() / ("Library/Application Support" if sys.platform == "darwin" else "Documents")
    return base / "MesenCE" / "LiveRecording"


def geometry_scale(width, height):
    """Integer uniform scale of a captured frame back to the native NES plane,
    or None when the geometry is not a clean multiple (unexpected for a capture
    the emulator itself scaled)."""
    if width and height and width % NATIVE_W == 0 and height % NATIVE_H == 0:
        sx, sy = width // NATIVE_W, height // NATIVE_H
        if sx == sy:
            return sx
    return None


def parse_ppm_geometry(path):
    """(width, height) from a P6 PPM header. Reads only the header bytes; the
    pixels stay on disk for tk.PhotoImage."""
    with open(path, "rb") as f:
        magic = f.readline().strip()
        dims = f.readline().split()
        if magic != b"P6" or len(dims) != 2:
            raise ValueError(f"{path.name} is not a P6 PPM (bad header)")
        return int(dims[0]), int(dims[1])


def parse_sprites_json(text):
    """Validate and normalise one sprites.json into a plain dict. Raises
    ValueError with a reader-facing message when the file is not what ADR-0169
    section 2 publishes (atomic rename means a torn file is impossible, but a
    foreign file is)."""
    data = json.loads(text)
    palette = data["palette"]
    oam = data["oam"]
    if len(palette) != 0x20 or len(oam) != 64:
        raise ValueError("sprites.json is not an ADR-0169 sprite record")
    if any(len(entry) != 4 for entry in oam):
        raise ValueError("sprites.json OAM entry is not [y, tile, attr, x]")
    # Raw OAM layout: each entry is [y, tile, attr, x].
    return {
        "frame": int(data["frame"]),
        "captureFrame": int(data["captureFrame"]),
        "patternAddr": int(data["patternAddr"]) & 0x1000,
        "largeSprites": bool(data["largeSprites"]),
        "spritesEnabled": bool(data["spritesEnabled"]),
        "leftColumnClip": bool(data["leftColumnClip"]),
        "palette": list(palette),
        "oam": oam,
    }


def parse_background_json(text):
    """Validate and normalise one background.json into a plain dict (ADR-0169
    2026-09-08 update). tmpScroll is loopy "t" — the scroll the game wrote — the
    base the background must be laid out from; recordings produced before the
    field was renamed carried the same value under "videoRamAddr", so both keys
    are accepted."""
    data = json.loads(text)
    for key in ("patternAddr", "enabled", "leftColumnClip", "fineScrollX"):
        if key not in data:
            raise ValueError("background.json is not an ADR-0169 background record")
    return {
        "patternAddr": int(data["patternAddr"]) & 0x1000,
        "enabled": bool(data["enabled"]),
        "leftColumnClip": bool(data["leftColumnClip"]),
        "tmpScroll": int(data.get("tmpScroll", data.get("videoRamAddr", 0))) & 0x7FFF,
        "fineScrollX": int(data["fineScrollX"]) & 0x07,
    }


def parse_scanline_scroll(raw):
    """240 per-scanline scroll snapshots (uint32 LE), one per visible scanline -
    written by both producers alongside nametables.bin (2026-09-08 ADR-0169
    update, "mid-frame raster splits"; see BaseNesPpu::GetScanlineScrollTrace's
    own comment on the array's semantics). Each value packs loopy v (bits 0-14,
    the same bit layout as tmpScroll) with that row's fine X (bits 15-17) and
    background pattern table select bit (bit 18). A raster effect that
    rewrites either mid-frame - Life Force's diagonal parallax (fine X),
    Gauntlet's title screen splitting its background graphics into two CHR
    halves via a bare $2000 write (pattern table select) - would be invisible
    to a v-only trace, since neither bit lives inside v/t's own bits. Absent
    for a recording made before this update; callers fall back to the single
    background.json tmpScroll/patternAddr then."""
    import struct
    count = len(raw) // 4
    return list(struct.unpack(f"<{count}I", raw[:count * 4]))


def parse_scanline_chr_bank(raw):
    """240 rows * 32 slots of CHR-ROM byte offsets (uint32 LE), flat in the
    same layout BaseNesPpu::_scanlineChrBankOffsets publishes - written by
    both producers alongside scanlinescroll.bin (2026-09-08 ADR-0169 update,
    "mid-frame CHR bank splits"; see LiveRecordFormat.h's ScanlineChrBank
    comment). Row py's slot s (s in 0..0x1F, the 256-byte PPU-side page
    $0000-$1FFF is addressed in) holds the byte offset into chrfull.bin that
    page resolved to while scanline py rendered; 0xFFFFFFFF marks a page the
    mapper does not back with CHR-ROM right now (CHR-RAM, or none at all), for
    which the flat chr.bin snapshot stays authoritative. Index it as
    rows[py * 0x20 + slot]. Absent for a recording made before this update or
    for a CHR-RAM mapper - callers fall back to the single chr.bin snapshot."""
    import struct
    count = len(raw) // 4
    return list(struct.unpack(f"<{count}I", raw[:count * 4]))


def decode_scroll_row(t):
    """One scanline's (world_x_base, world_y, pattern_addr) from a packed
    per-scanline snapshot (parse_scanline_scroll): fine X (bits 15-17),
    background pattern table select (bit 18, 0 or 0x1000) plus loopy v's own
    bits - NT select (10-11), coarse X/Y (0-4 / 5-9), fine Y (12-14). world_y
    is the exact nametable row this scanline fetches (v already walked there
    one row at a time), so - unlike a single frame-wide scroll - no per-row
    "+py" accumulation is needed on top of it."""
    fine_x = (t >> 15) & 0x07
    pattern_addr = 0x1000 if (t >> 18) & 1 else 0
    coarse_x = t & 0x1F
    h_sel = (t >> 10) & 1
    coarse_y = (t >> 5) & 0x1F
    v_sel = (t >> 11) & 1
    fine_y = (t >> 12) & 7
    world_x = h_sel * 256 + coarse_x * 8 + fine_x
    world_y = v_sel * 240 + coarse_y * 8 + fine_y
    return world_x, world_y, pattern_addr


def parse_chrlatch_json(text):
    """Validate and normalise one chrlatch.json into a plain dict (ADR-0169
    2026-09-08 "MMC2/MMC4 CHR-latch" update). Published only for a mapper
    whose CHR bank flips mid-frame via a tile-index latch (BaseMapper::
    HasChrBankLatch — Mike Tyson's/Super Mac's Punch-Out); its absence for
    every other mapper is not an error, callers just skip the latch-aware
    reconstruction path."""
    data = json.loads(text)
    for key in ("pageSize", "leftFdBank", "leftFeBank", "rightFdBank", "rightFeBank"):
        if key not in data:
            raise ValueError("chrlatch.json is not an ADR-0169 CHR-latch record")
    return {
        "pageSize": int(data["pageSize"]),
        "leftFdBank": int(data["leftFdBank"]),
        "leftFeBank": int(data["leftFeBank"]),
        "rightFdBank": int(data["rightFdBank"]),
        "rightFeBank": int(data["rightFeBank"]),
    }


def deduce_initial_chr_latch(chr_flat, chr_full, latch):
    """Best-guess starting latch value (0 selects the "FD" bank, 1 selects
    the "FE" bank — MMC2.h's own naming) for each CHR half, from chr.bin (the
    single end-of-frame-resolved snapshot every mapper publishes) compared
    against the two banks chrfull.bin says the latch could have picked.

    This is a guess, not a proof, because chr.bin only tells us the LAST value
    the latch held in this half during the whole frame — not what it started
    the frame holding. But MMC2's own latch update (NotifyVramAddressChange)
    is an unconditional overwrite, never a toggle: latch=0 whenever tile 0xFD
    is fetched through this half, latch=1 whenever tile 0xFE is, regardless of
    what it held before. So a wrong starting guess self-heals at this half's
    first FD/FE fetch in the frame, and is only wrong for whatever this half
    draws BEFORE that first fetch — the guess is exactly right whenever there
    is no such fetch (the common case: the latch never flips this frame, so
    "last value" and "starting value" are the same value)."""
    page = latch["pageSize"]

    def guess(flat_half, fd_bank, fe_bank):
        fd_bytes = chr_full[fd_bank * page:(fd_bank + 1) * page]
        fe_bytes = chr_full[fe_bank * page:(fe_bank + 1) * page]
        fd_score = sum(1 for a, b in zip(flat_half, fd_bytes) if a == b)
        fe_score = sum(1 for a, b in zip(flat_half, fe_bytes) if a == b)
        return 0 if fd_score >= fe_score else 1

    left = guess(chr_flat[0x0000:0x1000], latch["leftFdBank"], latch["leftFeBank"])
    right = guess(chr_flat[0x1000:0x2000], latch["rightFdBank"], latch["rightFeBank"])
    return left, right


def build_planes_with_chr_latch(bg, nametables, sprites, chr_full, latch, initial_left, initial_right, scanline_scroll=None):
    """Background + sprite planes for a frame from a CHR-latch mapper (MMC2/
    MMC4 — BaseMapper::HasChrBankLatch, e.g. Mike Tyson's Punch-Out's boxer
    portrait), used instead of build_background_plane/build_sprite_planes
    when chrlatch.json/chrfull.bin are on the wire.

    A single flat chr.bin snapshot only ever holds whichever bank the latch
    last resolved to per half — wrong for any tile drawn earlier in the frame
    under the other bank. This walks the frame in the 2C02's own fetch order —
    a row's background tiles, then that row's up-to-8 visible sprites in OAM
    order, same as real hardware pipelines them — because the latch is one
    piece of state shared by both layers: whichever layer fetches tile 0xFD or
    0xFE last decides what every following fetch through that half sees, until
    the next 0xFD/0xFE. initial_left/initial_right (see
    deduce_initial_chr_latch) seed the two halves' starting state.

    Returns (bg_plane, bg_opaque, sp_plane, sp_behind, touched) — the same
    shapes build_background_plane/build_sprite_planes produce, so
    compose_reconstruction and sprite_boxes work unchanged.

    Known limitation: an 8x16 sprite picks its pattern-table half per tile
    from bit 0 of its own tile index, not from sprites['patternAddr']; the
    fetch-order simulation below approximates the second (bottom) tile of an
    8x16 sprite as index+1 in the SAME half as the top tile; a real 8x16 CHR-
    latch title stitching top/bottom across halves would need per-tile half
    resolution. Not exercised by Punch-Out (its sprites are 8x8)."""
    page = latch["pageSize"]
    banks = {0: (latch["leftFdBank"], latch["leftFeBank"]),
             1: (latch["rightFdBank"], latch["rightFeBank"])}
    latch_state = {0: initial_left, 1: initial_right}

    def fetch(half, tile_index, row_in_tile):
        bank = banks[half][latch_state[half]]
        base = bank * page + (tile_index << 4)
        low = chr_full[base + row_in_tile]
        high = chr_full[base + row_in_tile + 8]
        # The trigger fires as a side effect of THIS fetch, so it never
        # changes the bank THIS tile itself is drawn from — only the next
        # tile fetched through this half sees the new value (MMC2.h's
        # NotifyVramAddressChange runs on the address the PPU just put on
        # the bus, after the byte at that address was already latched in).
        if tile_index == 0xFD:
            latch_state[half] = 0
        elif tile_index == 0xFE:
            latch_state[half] = 1
        return low, high

    bg_plane = bytearray(NATIVE_W * NATIVE_H)
    bg_opaque = bytearray(NATIVE_W * NATIVE_H)
    sp_plane = bytearray(NATIVE_W * NATIVE_H)
    sp_behind = bytearray(NATIVE_W * NATIVE_H)
    touched = [False] * len(sprites["oam"])

    bg_enabled = bg is not None and bg["enabled"]
    bg_half = (bg["patternAddr"] >> 12) & 1 if bg_enabled else None
    sp_half = (sprites["patternAddr"] >> 12) & 1
    large = sprites["largeSprites"]
    size = 16 if large else 8
    size_mask = size - 1
    clip_left_sp = sprites["leftColumnClip"]
    oam = sprites["oam"]

    if bg_enabled:
        t = bg["tmpScroll"]
        fine_x0 = bg["fineScrollX"]
        scroll_x = ((t >> 10) & 1) * 256 + (t & 0x1F) * 8 + fine_x0
        scroll_y = ((t >> 11) & 1) * 240 + ((t >> 5) & 0x1F) * 8 + ((t >> 12) & 7)
    has_trace = scanline_scroll is not None and len(scanline_scroll) == NATIVE_H
    clip_left_bg = bg["leftColumnClip"] if bg_enabled else False

    for row_y in range(NATIVE_H):
        # ---- this row's background tiles, left to right (fetched first — see
        # this function's docstring on fetch order) ----
        if bg_enabled:
            # 2026-09-08 ADR-0169 update ("mid-frame raster splits") - see
            # build_background_plane's docstring on scanline_scroll. Each trace
            # value already packs its row's own fine X (bits 15-17) and
            # background pattern table select (bit 18), so no frame-wide
            # fine_x0/bg_half is applied on top of it.
            if has_trace:
                row_wx, world_y, row_pattern_addr = decode_scroll_row(scanline_scroll[row_y])
                row_bg_half = (row_pattern_addr >> 12) & 1
            else:
                row_wx = scroll_x
                world_y = scroll_y + row_y
                if world_y >= 480:
                    world_y -= 480
                row_bg_half = bg_half
            v_sel, y_in_page = divmod(world_y, 240)
            row_in_nt, fine_y = divmod(y_in_page, 8)
            page_base = v_sel << 11
            row_base = row_in_nt * 32
            attr_row = (row_in_nt >> 2) * 8
            quad_y = (row_in_nt & 2) << 1
            out_row = row_y * NATIVE_W
            p = 0
            wx = row_wx
            while p < NATIVE_W:
                col_world = (wx >> 3) & 0x3F
                h_sel = col_world >> 5
                col_in_nt = col_world & 0x1F
                tile_index = nametables[page_base + h_sel * 0x400 + row_base + col_in_nt]
                attr = nametables[page_base + h_sel * 0x400 + 0x3C0 + attr_row + (col_in_nt >> 2)]
                subpal = ((attr >> (quad_y | (col_in_nt & 2))) & 3) << 2
                low, high = fetch(row_bg_half, tile_index, fine_y)
                run = 8 - (wx & 7)
                if p + run > NATIVE_W:
                    run = NATIVE_W - p
                for _ in range(run):
                    bit = 7 - (wx & 7)
                    color = ((high >> bit) & 1) << 1 | ((low >> bit) & 1)
                    if color:
                        bg_plane[out_row + p] = subpal + color
                        bg_opaque[out_row + p] = 1
                    p += 1
                    wx += 1
            if clip_left_bg:
                bg_plane[out_row:out_row + 8] = b"\x00" * 8
                bg_opaque[out_row:out_row + 8] = b"\x00" * 8

        # ---- this row's sprites, OAM order, hardware's 8-per-scanline cap
        # (fetched after the background — see this function's docstring) ----
        visible = []
        for i, (y0, _tile, _attr, _x) in enumerate(oam):
            if y0 >= HIDDEN_SPRITE_Y:
                continue
            if y0 <= row_y < y0 + size:
                visible.append(i)
                if len(visible) >= 8:
                    break
        for i in visible:
            y0, tile, attr, x = oam[i]
            behind_attr = bool(attr & 0x20)
            h_mirror = bool(attr & 0x40)
            v_mirror = bool(attr & 0x80)
            palette_base = ((attr & 3) << 2) | 0x10
            sy = row_y - y0
            tile_row = (sy ^ size_mask) if v_mirror else sy
            if large:
                half = tile & 1
                base_tile = tile & ~1
                if tile_row >= 8:
                    tile_row -= 8
                    fetch_tile = base_tile + 1
                else:
                    fetch_tile = base_tile
            else:
                half = sp_half
                fetch_tile = tile
            low, high = fetch(half, fetch_tile, tile_row)
            for dx in range(8):
                bit = dx if h_mirror else 7 - dx
                color = ((high >> bit) & 1) << 1 | ((low >> bit) & 1)
                if not color:
                    continue
                cx = x + dx
                if cx >= NATIVE_W or (clip_left_sp and cx < 8):
                    continue
                cell = row_y * NATIVE_W + cx
                if sp_plane[cell] == 0:
                    sp_plane[cell] = palette_base + color
                    sp_behind[cell] = 1 if behind_attr else 0
                    touched[i] = True
    return bg_plane, bg_opaque, sp_plane, sp_behind, touched


def load_colors(path):
    """The run's 64 RGB colors (palette.json), as (r, g, b) tuples indexed by
    NES color number 0x00-0x3F."""
    data = json.loads(path.read_text())
    colors = data["colors"]
    if len(colors) != 64:
        raise ValueError(f"{path.name} does not carry the 64-color table")
    out = []
    for c in colors:
        out.append((int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)))
    return out


def _tile_base(tile, large, pattern_addr):
    """Absolute chr.bin address of a sprite's first 8x8 tile row (ADR-0169 /
    NesPpu::LoadSprite)."""
    if large:
        # Bit 0 of the tile selects the pattern table; the remaining bits index
        # a pair of 8x8 tiles that make the 8x16 sprite.
        return ((tile & 1) << 12) | ((tile & ~1) << 4)
    return pattern_addr | (tile << 4)


def build_sprite_planes(sprites, chr_bytes, show_front=True, show_behind=True):
    """Sprite layer at native 256x240. plane[i] holds the palette-RAM slot of
    the winning sprite pixel (0 = none); behind[i] (0/1) carries that winner's
    OAM attribute bit 5 ("behind background"), which is what compose_reconstruction
    needs to multiplex sprites over the background the way the 2C02 does. OAM
    order decides overlap: a lower OAM index has priority (drawn on top), so
    ascending order and first-write-wins reproduce it, and the first writer is
    the winner whose priority bit is kept.

    show_front/show_behind filter by that same attribute bit — the two layers
    the viewer's checkboxes hide independently. A filtered-out sprite is
    skipped entirely, so it puts down no pixel and stays untouched (no bounding
    box either, since sprite_boxes reads touched). The mask bit
    sprites['leftColumnClip'] is honoured (a sprite is not shown in the screen's
    first 8 columns while it is set), because the frame above clips it too.

    Returns (plane, behind, touched): touched[i] says OAM sprite i put down at
    least one pixel — a sprite whose whole tile is transparent never shows, so
    it should not be outlined either."""
    plane = bytearray(NATIVE_W * NATIVE_H)
    behind = bytearray(NATIVE_W * NATIVE_H)
    touched = [False] * len(sprites["oam"])
    large = sprites["largeSprites"]
    size = 16 if large else 8
    size_mask = size - 1
    pattern_addr = sprites["patternAddr"]
    clip_left = sprites["leftColumnClip"]
    oam = sprites["oam"]

    for i, (y0, tile, attr, x) in enumerate(oam):
        if y0 >= HIDDEN_SPRITE_Y:
            continue  # wrapped below the visible area - the PPU never shows it
        behind_attr = bool(attr & 0x20)
        if behind_attr and not show_behind:
            continue
        if not behind_attr and not show_front:
            continue
        h_mirror = bool(attr & 0x40)
        v_mirror = bool(attr & 0x80)
        palette_base = ((attr & 3) << 2) | 0x10

        top = max(0, y0)
        bottom = min(NATIVE_H, y0 + size)
        for row_y in range(top, bottom):
            sy = row_y - y0
            tile_row = (sy ^ size_mask) if v_mirror else sy  # LoadSprite flip
            if large:
                base = _tile_base(tile, True, pattern_addr)
                if tile_row >= 8:
                    base += 0x10  # second 8x8 half of the 8x16 sprite
                    tile_row -= 8
            else:
                base = _tile_base(tile, False, pattern_addr)
            low = chr_bytes[base + tile_row]
            high = chr_bytes[base + tile_row + 8]

            # Shifter outputs MSB-first: display column dx reads original bit
            # (7 - dx); a horizontal mirror reverses the byte first, so dx reads
            # original bit dx.
            for dx in range(8):
                bit = dx if h_mirror else 7 - dx
                color = ((high >> bit) & 1) << 1 | ((low >> bit) & 1)
                if not color:
                    continue  # transparent
                cx = x + dx
                if cx >= NATIVE_W or (clip_left and cx < 8):
                    continue
                cell = row_y * NATIVE_W + cx
                if plane[cell] == 0:
                    plane[cell] = palette_base + color  # 0x11..0x1F, never 0
                    behind[cell] = 1 if behind_attr else 0
                    touched[i] = True
    return plane, behind, touched


def build_background_plane(bg, nametables, chr_bytes, scanline_scroll=None,
                           scanline_chr_bank=None, chr_rom_full=None):
    """Background layer at native 256x240, as (plane, opaque): plane[i] is the
    pixel's palette-RAM slot (0 = the universal backdrop color), opaque[i] is 1
    when the pixel comes from a tile's own 2-bit color — a behind-background
    sprite is hidden behind exactly those pixels. bg['enabled'] false renders
    the whole screen as backdrop (so every behind sprite shows, like the real
    mask bit); bg['leftColumnClip'] blanks the first 8 screen columns to
    backdrop.

    nametables is the recorder's $2000-$2FFF read, taken under the same lock as
    the sprite layer, so mirroring is already resolved: byte
    (page << 10) + offset reproduces what the PPU fetches at that nametable
    page, where page = vertical_select*2 + horizontal_select.

    scanline_scroll (2026-09-08 ADR-0169 update, "mid-frame raster splits"):
    240 per-row snapshots (parse_scanline_scroll), used instead of one
    frame-wide scroll/pattern-table whenever present - each row decodes its
    OWN world_y/world_x_base/pattern-table select from its own snapshot
    (decode_scroll_row), so a status-bar split, a raster-parallax rewrite, or
    a bare $2000 pattern-table split reproduces correctly instead of the whole
    screen assuming bg['tmpScroll']/bg['patternAddr']'s single end-of-frame
    value. Absent (None, or the wrong length) for a recording made before this
    update - the caller then gets the old single-scroll behavior, unchanged.

    scanline_chr_bank + chr_rom_full (2026-09-08 ADR-0169 update, "mid-frame
    CHR bank splits"): the per-scanline CHR-ROM offset trace
    (parse_scanline_chr_bank) and the raw CHR-ROM it indexes into. The plain
    chr_bytes snapshot (chr.bin) only ever holds whichever CHR banks were in
    effect at end of frame - wrong for any row drawn before a mapper rewrote
    its CHR bank registers mid-frame (Gauntlet's title screen splits one
    nametable's tile indices across two different sets of actual graphics via
    plain $8000/$8001 writes at scanline ~119, no scanline IRQ). When both are
    present and the trace is the full 240*32 entries, each tile's two bitplane
    bytes (which always share one 256-byte CHR page - a tile is 16-byte
    aligned) are read from chr_rom_full at that row's recorded page offset;
    a 0xFFFFFFFF page (CHR-RAM, or not ROM-backed) falls back to chr_bytes,
    which DebugReadVram already resolved for it. Absent for a CHR-RAM mapper
    or a recording made before this update - unchanged single-snapshot
    behavior."""
    plane = bytearray(NATIVE_W * NATIVE_H)
    opaque = bytearray(NATIVE_W * NATIVE_H)
    if not bg["enabled"]:
        return plane, opaque

    fine_x0 = bg["fineScrollX"]
    t = bg["tmpScroll"]
    scroll_x = ((t >> 10) & 1) * 256 + (t & 0x1F) * 8 + fine_x0
    scroll_y = ((t >> 11) & 1) * 240 + ((t >> 5) & 0x1F) * 8 + ((t >> 12) & 7)
    has_trace = scanline_scroll is not None and len(scanline_scroll) == NATIVE_H
    has_chr_trace = (scanline_chr_bank is not None and chr_rom_full is not None
                     and len(scanline_chr_bank) == NATIVE_H * 0x20)
    pattern = bg["patternAddr"]
    nt = nametables

    # World space is 512x480 (2x2 nametable pages), but a page is 256x240 -
    # 32 tile columns by *30* tile rows, not 32: a nametable's bytes for tile
    # rows 30-31 hold no tile data (IncVerticalScrolling wraps coarse Y at 29,
    # not 31). scroll_y/world_y above are already built on that 240-per-page
    # basis, so page/row-in-page here must come from a divmod by 240/30, not a
    # bit shift assuming 256/32 - mixing the two silently reads the wrong page.
    for py in range(NATIVE_H):
        if has_trace:
            row_wx, world_y, row_pattern = decode_scroll_row(scanline_scroll[py])
        else:
            row_wx = scroll_x
            world_y = scroll_y + py
            if world_y >= 480:
                world_y -= 480  # a 256-tall viewport never crosses more than one edge
            row_pattern = pattern
        v_sel, y_in_page = divmod(world_y, 240)
        row_in_nt, fine_y = divmod(y_in_page, 8)
        page_base = (v_sel << 11)  # vertical select is address bit 11
        row_base = row_in_nt * 32
        attr_row = (row_in_nt >> 2) * 8
        quad_y = (row_in_nt & 2) << 1
        out_row = py * NATIVE_W
        p = 0
        wx = row_wx
        while p < NATIVE_W:
            # The screen's columns are the world's columns starting at scroll_x;
            # each loop body decodes one 8px tile, then advances past it. A page
            # is 256 wide (32 tile columns), so this axis IS a clean power of
            # two and a shift/mask is exact.
            col_world = (wx >> 3) & 0x3F
            h_sel = col_world >> 5
            col_in_nt = col_world & 0x1F
            tile_index = nt[page_base + h_sel * 0x400 + row_base + col_in_nt]
            attr = nt[page_base + h_sel * 0x400 + 0x3C0 + attr_row + (col_in_nt >> 2)]
            subpal = ((attr >> (quad_y | (col_in_nt & 2))) & 3) << 2
            ta = row_pattern + (tile_index << 4) + fine_y
            if has_chr_trace:
                # A tile's two bitplane bytes share one 256-byte CHR page (the
                # tile is 16-byte aligned), so one slot lookup covers both - see
                # this function's docstring for the 0xFFFFFFFF fallback.
                bank_off = scanline_chr_bank[py * 0x20 + (ta >> 8)]
                in_page = ta & 0xFF
                if bank_off != 0xFFFFFFFF and bank_off + in_page + 8 <= len(chr_rom_full):
                    low = chr_rom_full[bank_off + in_page]
                    high = chr_rom_full[bank_off + in_page + 8]
                else:
                    low = chr_bytes[ta]
                    high = chr_bytes[ta + 8]
            else:
                low = chr_bytes[ta]
                high = chr_bytes[ta + 8]
            run = 8 - (wx & 7)  # pixels left in this tile before the next one
            if p + run > NATIVE_W:
                run = NATIVE_W - p
            for k in range(run):
                bit = 7 - (wx & 7)
                color = ((high >> bit) & 1) << 1 | ((low >> bit) & 1)
                if color:
                    plane[out_row + p] = subpal + color  # backdrop = 0
                    opaque[out_row + p] = 1
                p += 1
                wx += 1
    if bg["leftColumnClip"]:
        for py in range(NATIVE_H):
            start = py * NATIVE_W
            plane[start:start + 8] = b"\x00" * 8
            opaque[start:start + 8] = b"\x00" * 8
    return plane, opaque


def empty_background_plane():
    """A fully-backdrop background (enabled=false): every pixel slot 0, nothing
    opaque — so every sprite, front or behind, draws. Used when the recording
    has no background layer yet, or the user hid it."""
    return bytearray(NATIVE_W * NATIVE_H), bytearray(NATIVE_W * NATIVE_H)


def compose_reconstruction(bg_plane, bg_opaque, sp_plane, sp_behind):
    """Merge the two planes the way the 2C02's priority logic does. sp_plane
    already holds the winning (lowest-OAM-index) sprite per cell — 0 where none.
    Per pixel: a front sprite always wins; a behind sprite wins only where the
    background is the backdrop (opaque 0); otherwise the background shows.
    Output is a single palette-RAM-indexed plane, 0x00..0x1F, ready for
    make_palette_ppm."""
    out = bytearray(len(bg_plane))
    for i, slot in enumerate(sp_plane):
        if slot and (not sp_behind[i] or not bg_opaque[i]):
            out[i] = slot
        else:
            out[i] = bg_plane[i]
    return out


def make_palette_ppm(plane, palette_ram, colors):
    """A palette-RAM-indexed plane (every cell a real color: slot 0 is the
    universal backdrop palette_ram[0], never a "no pixel" sentinel) as a native
    256x240 P6 PPM through the run's color table. The GUI zooms this to the
    composite's geometry."""
    out = bytearray(b"P6\n%d %d\n255\n" % (NATIVE_W, NATIVE_H))
    for slot in plane:
        r, g, b = colors[palette_ram[slot] & 0x3F]
        out += bytes((r, g, b))
    return bytes(out)


def sprite_boxes(sprites, touched):
    """(x, y, w, h) of the OAM sprites that put at least one pixel down, for
    bounding boxes on the composite pane. Empty (transparent) tiles and sprites
    wrapped off the bottom of the screen never show, so they get no box."""
    large = sprites["largeSprites"]
    size = 16 if large else 8
    for i, (y0, _tile, _attr, x) in enumerate(sprites["oam"]):
        if touched[i]:
            yield (x, y0, size, size)

class RecordViewerApp:
    """The window: a source toolbar, a view toolbar, the two panes, a notes
    strip and a status strip.

    The panes are the point, so they own every pixel the toolbars do not: each
    is a header line (title, and the PPU/geometry meta for that frame), a
    canvas that fills whatever is left with the frame centred in it, and its
    own layer toggles right under it. Both panes always draw at the same zoom
    — they exist to be compared pixel for pixel — and the zoom either fits the
    window or is the one the user picked. Every number and every string in
    here comes from record_viewer_layout, which is testable without a display.
    """

    POLL_MS = 100
    RESIZE_DEBOUNCE_MS = 80
    CANVAS_BG = "#101010"
    CANVAS_BORDER = "#2b2b2b"
    META_FG = "#8a8a8a"
    BADGE_COLORS = {"REC": ("#b5342b", "#ffffff"),
                    "STOPPED": ("#4a4a4a", "#e8e8e8"),
                    "PAUSED": ("#7a5c00", "#ffffff"),
                    "IDLE": ("#3a3a3a", "#b0b0b0")}

    def __init__(self, root: tk.Tk, live_dir: Path):
        self.root = root
        self.live_dir = live_dir
        self._rom = ""
        root.title(vl.window_title(""))
        root.minsize(760, 560)

        self._composite_img = None   # PhotoImage on screen (Tk drops it on GC)
        self._pane_img = None        # ditto, reconstruction pane
        self._seen = {}          # {path: (mtime_ns, size)} of the last draw
        self._status_text = None
        self._notice_text = ""
        self._last_mark_data = None  # (sprites, touched) of the last draw
        self._last_sprite_state = None  # (sprites, chr, colors, w, h, scale) of the last draw
        self._last_bg_state = None   # (bg dict, nametables bytes, scanlineScroll list-or-None,
                                     #  scanlineChrBank list-or-None, chrfull bytes-or-None) of the last draw, or None
        self._last_chrlatch_state = None  # (chrlatch dict, chrfull bytes) of the last draw, or None
        self._composite_raw = None      # unzoomed PhotoImage decoded from frame.ppm
        self._composite_native_wh = None  # (w, h) of frame.ppm, before display zoom
        self._display_zoom = 1          # shared zoom applied on top of the recorder's own scale
        self._resize_job = None
        self._orientation = None
        self._headers = []   # (header frame, title, subtitle, meta) per pane

        self._build_fonts()
        self._build_source_bar()
        self._build_view_bar()
        self._build_body()
        self._build_notes()
        self._build_status_bar()
        self._bind_keys()

        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)   # the panes take the slack
        root.bind("<Configure>", self._schedule_resize)
        self.root.after(self.POLL_MS, self._poll)

    # ---- chrome ------------------------------------------------------------

    def _build_fonts(self):
        base = tkfont.nametofont("TkDefaultFont")
        family, size = base.cget("family"), int(base.cget("size"))
        self.font_title = tkfont.Font(family=family, size=size, weight="bold")
        self.font_meta = tkfont.Font(family=family, size=max(9, size - 1))
        self.font_badge = tkfont.Font(family=family, size=max(9, size - 1), weight="bold")
        style = ttk.Style(self.root)
        style.configure("Meta.TLabel", foreground=self.META_FG)

    def _build_source_bar(self):
        """Row 0 — what we are watching. The entry takes the slack so a long
        path stays readable when the window grows."""
        bar = ttk.Frame(self.root, padding=(8, 8, 8, 2))
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)

        ttk.Label(bar, text="Live dir").grid(row=0, column=0, padx=(0, 6))
        self.live_dir_var = tk.StringVar(value=str(self.live_dir))
        self.live_dir_entry = ttk.Entry(bar, textvariable=self.live_dir_var)
        self.live_dir_entry.grid(row=0, column=1, sticky="ew")
        self.live_dir_entry.bind("<Return>", lambda _e: self._attach())
        ttk.Button(bar, text="Browse…", width=9, command=self._browse).grid(row=0, column=2, padx=(6, 0))
        self.attach_btn = ttk.Button(bar, text="Attach", width=8, command=self._attach)
        self.attach_btn.grid(row=0, column=3, padx=(4, 0))

        ttk.Separator(bar, orient="vertical").grid(row=0, column=4, sticky="ns", padx=10)
        self.pause_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Pause", variable=self.pause_var,
                        command=self._on_pause_toggled).grid(row=0, column=5)
        ttk.Button(bar, text="Poll now", width=9, command=self._poll_now).grid(row=0, column=6, padx=(6, 0))

    def _build_view_bar(self):
        """Row 1 — how it is shown: the split, the zoom, the notes strip. The
        two frames are always drawn at one zoom, so this is one control, not
        one per pane."""
        bar = ttk.Frame(self.root, padding=(8, 2, 8, 2))
        bar.grid(row=1, column=0, sticky="ew")
        bar.columnconfigure(7, weight=1)

        ttk.Label(bar, text="Layout").grid(row=0, column=0, padx=(0, 6))
        self.layout_var = tk.StringVar(value=dict(vl.LAYOUT_LABELS)[vl.LAYOUT_AUTO])
        self.layout_box = ttk.Combobox(bar, textvariable=self.layout_var, width=12,
                                       state="readonly",
                                       values=[label for _mode, label in vl.LAYOUT_LABELS])
        self.layout_box.grid(row=0, column=1)
        self.layout_box.bind("<<ComboboxSelected>>", lambda _e: self._relayout())

        ttk.Separator(bar, orient="vertical").grid(row=0, column=2, sticky="ns", padx=10)
        ttk.Label(bar, text="Zoom").grid(row=0, column=3, padx=(0, 6))
        self.fit_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Fit", variable=self.fit_var,
                        command=self._on_fit_toggled).grid(row=0, column=4)
        self.zoom_var = tk.IntVar(value=2)
        self.zoom_spin = ttk.Spinbox(bar, from_=vl.MIN_ZOOM, to=vl.MAX_ZOOM, width=4,
                                     textvariable=self.zoom_var, state="disabled",
                                     command=self._on_zoom_changed)
        self.zoom_spin.grid(row=0, column=5, padx=(6, 0))
        self.zoom_readout = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.zoom_readout, style="Meta.TLabel",
                  font=self.font_meta).grid(row=0, column=6, padx=(6, 0))

        self.notes_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Notes", variable=self.notes_var,
                        command=self._on_notes_toggled).grid(row=0, column=8, sticky="e")

    def _build_body(self):
        self.body = ttk.Frame(self.root, padding=(8, 4, 8, 4))
        self.body.grid(row=2, column=0, sticky="nsew")

        self.composite_frame, self.composite_canvas, self.composite_meta, comp_tools = \
            self._make_pane(vl.COMPOSITE_TITLE, vl.COMPOSITE_SUBTITLE)
        self.mark_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(comp_tools, text="sprite boxes", variable=self.mark_var,
                        command=self._draw_marks_current).pack(side="left")

        self.sprite_frame, self.sprite_canvas, self.sprite_meta, rec_tools = \
            self._make_pane(vl.RECONSTRUCTION_TITLE, vl.RECONSTRUCTION_SUBTITLE)
        ttk.Label(rec_tools, text="layers:", style="Meta.TLabel",
                  font=self.font_meta).pack(side="left", padx=(0, 6))
        self.show_bg_var = tk.BooleanVar(value=True)
        self.bg_filter_check = ttk.Checkbutton(rec_tools, text="background",
                                               variable=self.show_bg_var,
                                               command=self._redraw_sprite_pane)
        self.bg_filter_check.pack(side="left")
        self.show_front_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(rec_tools, text="front sprites", variable=self.show_front_var,
                        command=self._redraw_sprite_pane).pack(side="left", padx=(8, 0))
        self.show_behind_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(rec_tools, text="behind sprites", variable=self.show_behind_var,
                        command=self._redraw_sprite_pane).pack(side="left", padx=(8, 0))

        self._apply_orientation(vl.ORIENT_HORIZONTAL)

    def _make_pane(self, title, subtitle):
        """One pane: header (title + live meta), the canvas that eats the
        slack, and a tool row underneath for that pane's own toggles."""
        frame = ttk.Frame(self.body)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(2, weight=1)
        title_label = ttk.Label(header, text=title, font=self.font_title)
        title_label.grid(row=0, column=0, sticky="w")
        subtitle_label = ttk.Label(header, text=subtitle, style="Meta.TLabel",
                                   font=self.font_meta)
        subtitle_label.grid(row=0, column=1, sticky="w", padx=(6, 0))
        meta = tk.StringVar()
        meta_label = ttk.Label(header, textvariable=meta, style="Meta.TLabel",
                               font=self.font_meta, anchor="e")
        meta_label.grid(row=0, column=2, sticky="e", padx=(12, 0))
        # The subtitle is the first thing to go when a pane gets narrow: the
        # meta is live data, the subtitle is a reminder (_fit_headers).
        self._headers.append((header, title_label, subtitle_label, meta_label))

        canvas = tk.Canvas(frame, background=self.CANVAS_BG, highlightthickness=1,
                           highlightbackground=self.CANVAS_BORDER,
                           width=NATIVE_W, height=NATIVE_H)
        canvas.grid(row=1, column=0, sticky="nsew", pady=(3, 0))
        canvas.bind("<Double-Button-1>", lambda _e: self._toggle_fit())
        canvas.bind("<Control-MouseWheel>", self._on_wheel_zoom)

        tools = ttk.Frame(frame)
        tools.grid(row=2, column=0, sticky="ew", pady=(3, 0))
        return frame, canvas, meta, tools

    def _build_notes(self):
        """Row 3 — the paragraph that says how to read the reconstruction. It
        spans the full window (so it wraps in two lines, not eight beside a
        pane) and folds away when the user does not need it."""
        self.notes_frame = ttk.Frame(self.root, padding=(8, 2, 8, 2))
        self.notes_frame.grid(row=3, column=0, sticky="ew")
        self.notes_frame.columnconfigure(0, weight=1)
        self.note_var = tk.StringVar(value="")
        self.note_label = ttk.Label(self.notes_frame, textvariable=self.note_var,
                                    style="Meta.TLabel", font=self.font_meta,
                                    justify="left", wraplength=900)
        self.note_label.grid(row=0, column=0, sticky="ew")

    def _build_status_bar(self):
        bar = ttk.Frame(self.root, padding=(8, 2, 8, 8))
        bar.grid(row=4, column=0, sticky="ew")
        bar.columnconfigure(2, weight=1)
        self.badge = tk.Label(bar, text="IDLE", font=self.font_badge, padx=6, pady=1)
        self.badge.grid(row=0, column=0)
        self._set_badge("IDLE")
        self.status = tk.StringVar(value="starting…")
        ttk.Label(bar, textvariable=self.status, style="Meta.TLabel").grid(
            row=0, column=1, sticky="w", padx=(8, 0))
        self.notice_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.notice_var, style="Meta.TLabel",
                  font=self.font_meta, anchor="e").grid(row=0, column=2, sticky="e")

    def _set_badge(self, name):
        bg, fg = self.BADGE_COLORS.get(name, self.BADGE_COLORS["IDLE"])
        self.badge.config(text=name, background=bg, foreground=fg)

    # ---- keyboard ----------------------------------------------------------

    def _bind_keys(self):
        """Shortcuts for everything on the toolbars, so watching a run does not
        mean travelling to a checkbox. Skipped while the path entry has focus —
        a path may contain any of these letters."""
        keys = {
            "<space>": self._toggle_pause,
            "p": self._toggle_pause,
            "r": self._poll_now,
            "m": lambda: self._flip(self.mark_var, self._draw_marks_current),
            "b": lambda: self._flip(self.show_bg_var, self._redraw_sprite_pane),
            "f": lambda: self._flip(self.show_front_var, self._redraw_sprite_pane),
            "h": lambda: self._flip(self.show_behind_var, self._redraw_sprite_pane),
            "n": lambda: self._flip(self.notes_var, self._on_notes_toggled),
            "l": self._cycle_layout,
            "0": self._zoom_fit,
            "plus": lambda: self._nudge_zoom(+1),
            "equal": lambda: self._nudge_zoom(+1),
            "minus": lambda: self._nudge_zoom(-1),
        }
        for key, fn in keys.items():
            seq = key if key.startswith("<") else f"<KeyPress-{key}>"
            self.root.bind(seq, self._typing_guard(fn))
        self.root.bind("<Control-o>", lambda _e: self._browse())
        self.root.bind("<Command-o>", lambda _e: self._browse())

    def _typing_guard(self, fn):
        def handler(_event=None):
            if self.root.focus_get() is self.live_dir_entry:
                return None
            fn()
            return "break"
        return handler

    @staticmethod
    def _flip(var, after):
        var.set(not var.get())
        after()

    # ---- view controls -----------------------------------------------------

    def _layout_mode(self):
        label = self.layout_var.get()
        for mode, text in vl.LAYOUT_LABELS:
            if text == label:
                return mode
        return vl.LAYOUT_AUTO

    def _cycle_layout(self):
        modes = [mode for mode, _label in vl.LAYOUT_LABELS]
        nxt = modes[(modes.index(self._layout_mode()) + 1) % len(modes)]
        self.layout_var.set(dict(vl.LAYOUT_LABELS)[nxt])
        self._relayout()

    def _relayout(self):
        self._apply_orientation(vl.pick_orientation(
            self._layout_mode(), self.root.winfo_width(), self.root.winfo_height()))
        self._schedule_resize()

    def _apply_orientation(self, orient):
        if orient == self._orientation:
            return
        self._orientation = orient
        for pane in (self.composite_frame, self.sprite_frame):
            pane.grid_forget()
        for i in (0, 1):
            self.body.columnconfigure(i, weight=0, uniform="")
            self.body.rowconfigure(i, weight=0, uniform="")
        if orient == vl.ORIENT_HORIZONTAL:
            self.composite_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
            self.sprite_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
            for i in (0, 1):
                self.body.columnconfigure(i, weight=1, uniform="pane")
            self.body.rowconfigure(0, weight=1)
        else:
            self.composite_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
            self.sprite_frame.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
            for i in (0, 1):
                self.body.rowconfigure(i, weight=1, uniform="pane")
            self.body.columnconfigure(0, weight=1)

    def _on_fit_toggled(self):
        self.zoom_spin.config(state="disabled" if self.fit_var.get() else "normal")
        if not self.fit_var.get():
            self.zoom_var.set(max(vl.MIN_ZOOM, self._display_zoom))
        self._redraw_both()

    def _toggle_fit(self):
        self._flip(self.fit_var, self._on_fit_toggled)

    def _zoom_fit(self):
        if not self.fit_var.get():
            self.fit_var.set(True)
            self._on_fit_toggled()

    def _on_zoom_changed(self):
        self.fit_var.set(False)
        self.zoom_spin.config(state="normal")
        self._redraw_both()

    def _nudge_zoom(self, delta):
        self.fit_var.set(False)
        self.zoom_spin.config(state="normal")
        self.zoom_var.set(vl.clamp_zoom(self._display_zoom + delta))
        self._redraw_both()

    def _on_wheel_zoom(self, event):
        self._nudge_zoom(+1 if event.delta > 0 else -1)
        return "break"

    def _on_notes_toggled(self):
        if self.notes_var.get():
            self.notes_frame.grid()
        else:
            self.notes_frame.grid_remove()

    def _on_pause_toggled(self):
        """Pause freezes the panes on the frame they hold — the run keeps
        going, this tool just stops reading it (it never writes, ADR-0169)."""
        self._refresh_status_strip()

    def _toggle_pause(self):
        self._flip(self.pause_var, self._on_pause_toggled)

    # ---- fill-the-window display zoom --------------------------------------

    def _schedule_resize(self, event=None):
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(self.RESIZE_DEBOUNCE_MS, self._on_resize)

    def _on_resize(self):
        self._resize_job = None
        self.note_label.config(wraplength=max(320, self.root.winfo_width() - 32))
        self._fit_headers()
        if self._layout_mode() == vl.LAYOUT_AUTO:
            self._apply_orientation(vl.pick_orientation(
                vl.LAYOUT_AUTO, self.root.winfo_width(), self.root.winfo_height()))
        self._redraw_both()

    def _redraw_both(self):
        self._redraw_composite_pane()
        self._draw_sprite_pane()
        self._fit_headers()

    def _fit_headers(self):
        """Keep a pane header legible at any width — grid does not shrink
        labels, it lets them overlap. Three states, widest first: title +
        subtitle + meta on one line; title + meta (the subtitle is a reminder,
        the meta is live data); title alone with the meta on a second line."""
        for header, title, subtitle, meta in self._headers:
            width = header.winfo_width()
            if width <= 1:
                continue
            title_w, meta_w = title.winfo_reqwidth(), meta.winfo_reqwidth()
            if title_w + subtitle.winfo_reqwidth() + meta_w + 24 <= width:
                subtitle.grid()
                meta.grid(row=0, column=2, columnspan=1, sticky="e", padx=(12, 0))
            elif title_w + meta_w + 24 <= width:
                subtitle.grid_remove()
                meta.grid(row=0, column=2, columnspan=1, sticky="e", padx=(12, 0))
            else:
                subtitle.grid_remove()
                meta.grid(row=1, column=0, columnspan=3, sticky="e", padx=0)

    def _canvas_room(self):
        """What both canvases can honour right now, minus their 1px border."""
        self.root.update_idletasks()
        return vl.shared_available([(c.winfo_width() - 4, c.winfo_height() - 4)
                                    for c in (self.composite_canvas, self.sprite_canvas)])

    def _compute_display_zoom(self, w, h):
        avail_w, avail_h = self._canvas_room()
        return vl.resolve_zoom(self.fit_var.get(), self.zoom_var.get(),
                               w, h, avail_w, avail_h)

    @staticmethod
    def _centre_image(canvas, image, tag):
        """Draw a frame centred in its canvas, and return the image's top-left
        in canvas coordinates (the sprite-box overlay needs that origin)."""
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        canvas.delete(tag)
        canvas.create_image(cw / 2, ch / 2, image=image, anchor="center", tags=tag)
        return ((cw - image.width()) / 2, (ch - image.height()) / 2)

    # ---- manual attach ----------------------------------------------------

    def _browse(self):
        """Pick a live directory with the platform's own chooser — typing a
        path is fine, but a headless run's <prefix>-live/ folder is buried."""
        start = self.live_dir if self.live_dir and Path(self.live_dir).is_dir() else Path.home()
        chosen = filedialog.askdirectory(title="Attach to a live recording folder",
                                         initialdir=str(start))
        if chosen:
            self.live_dir_var.set(chosen)
            self._attach()

    def _attach(self):
        """Point the viewer at a live directory the emulator (convention slot)
        or a terminal-launched headless run is publishing into."""
        text = self.live_dir_var.get().strip()
        if not text:
            return
        self.live_dir = Path(text)
        self._forget_frame_state()
        self._poll_now()

    def _forget_frame_state(self):
        """Drop everything cached about the frame on screen. Called when what we
        are watching changes — a different live directory, or the same slot
        after the human opened a different game (status.json's "rom"): every
        cache below is keyed to nothing but "the last poll", so a redraw that
        reuses one would resolve the new game's OAM/nametable bytes against the
        previous game's CHR and palette. The recorder empties the slot on the
        same event (LiveFrameRecorder::ClearSlot), for the same reason."""
        self._seen = {}
        self._status_text = None
        self._notice_text = ""
        self._last_mark_data = None
        self._last_sprite_state = None
        self._last_bg_state = None
        self._last_chrlatch_state = None
        self._composite_raw = None
        self._composite_native_wh = None

    def _poll_now(self):
        """The Poll now button / `r`: read once even while paused."""
        try:
            self._poll_once()
        except Exception as e:
            self.status.set(f"cannot read live data: {e}")

    # ---- polling -----------------------------------------------------------

    def _file_stamp(self, name):
        path = self.live_dir / name
        try:
            st = path.stat()
            return path, st.st_mtime_ns, st.st_size
        except OSError:
            return path, None, None

    def _read_once(self):
        """Read frame.ppm + sprites.json (+ chr.bin) + the background files at
        one poll; atomic renames keep each file whole, and reading them in the
        recorder's own publish order (frame, then sprites/chr, then
        background/nametables) keeps them on the same tick to within one publish
        interval. Returns a dict, or raises."""
        frame_path, fm_ns, fm_size = self._file_stamp("frame.ppm")
        if fm_ns is None:
            return None
        w, h = parse_ppm_geometry(frame_path)
        out = {"ppm": frame_path, "width": w, "height": h, "scale": geometry_scale(w, h)}
        sp_path, sp_ns, sp_size = self._file_stamp("sprites.json")
        if sp_ns is None:
            out["sprites"] = None
            return out
        out["sprites"] = parse_sprites_json((self.live_dir / "sprites.json").read_text())
        chr_path, chr_ns, chr_size = self._file_stamp("chr.bin")
        pal_path, pal_ns, pal_size = self._file_stamp("palette.json")
        if chr_ns is not None and pal_ns is not None:
            out["chr"] = chr_path.read_bytes()
            out["colors"] = load_colors(pal_path)
        # Background layer, when the recording carries it (2026-09-08 ADR-0169
        # update). background.json and nametables.bin are written together by the
        # recorder, so either being absent means this recording predates it.
        bg_path, bg_ns, _bg_size = self._file_stamp("background.json")
        if bg_ns is not None:
            try:
                out["background"] = parse_background_json((self.live_dir / "background.json").read_text())
                out["nametables"] = (self.live_dir / "nametables.bin").read_bytes()
            except (ValueError, OSError):
                out["background"] = None
                out["nametables"] = None
            # Per-scanline scroll trace (2026-09-08 ADR-0169 update, "mid-frame
            # raster splits") - absent for a recording made before this update;
            # None here just means build_background_plane falls back to the
            # single tmpScroll value, same as always.
            scroll_path, scroll_ns, _scroll_size = self._file_stamp("scanlinescroll.bin")
            out["scanlineScroll"] = parse_scanline_scroll(scroll_path.read_bytes()) if scroll_ns is not None else None
        # Raw CHR-ROM + per-scanline CHR-bank trace (2026-09-08 ADR-0169
        # update, "mid-frame CHR bank splits"). chrfull.bin is written by both
        # producers for ANY ROM-backed mapper (LiveRecordFormat.h's
        # ChrRomFull comment), so reading it cannot stay gated on
        # chrlatch.json's presence - that file only accompanies the MMC2/MMC4
        # latch case below. scanlinechrbank.bin goes out alongside it in the
        # same publish tick; both are absent only for a CHR-RAM mapper or a
        # recording made before this update.
        chrfull_path, chrfull_ns, _chrfull_size = self._file_stamp("chrfull.bin")
        out["chrfull"] = chrfull_path.read_bytes() if chrfull_ns is not None else None
        bank_path, bank_ns, _bank_size = self._file_stamp("scanlinechrbank.bin")
        if bank_ns is not None:
            out["scanlineChrBank"] = parse_scanline_chr_bank(bank_path.read_bytes())
        # CHR-latch record, present only for a mapper whose CHR bank flips via
        # a tile-index latch (BaseMapper::HasChrBankLatch — MMC2/MMC4); its
        # absence for every other mapper is not an error, the plain chr.bin
        # path (and scanlineChrBank above) covers those.
        out["chrlatch"] = None
        latch_path, latch_ns, _latch_size = self._file_stamp("chrlatch.json")
        if latch_ns is not None:
            try:
                out["chrlatch"] = parse_chrlatch_json((self.live_dir / "chrlatch.json").read_text())
            except (ValueError, OSError):
                out["chrlatch"] = None
        return out

    def _poll(self):
        if not self.pause_var.get():
            self._poll_now()
        self.root.after(self.POLL_MS, self._poll)

    def _refresh_status_strip(self):
        """Re-publish the strip's three fields (badge, run state, notices) from
        what the last poll left behind — also how Pause gets its own chip."""
        if self.pause_var.get():
            self._set_badge("PAUSED")
        if self._status_text is not None:
            self.status.set(self._status_text)
        self.notice_var.set(self._notice_text)

    def _poll_once(self):
        if self.live_dir is None:
            self._set_badge("IDLE")
            self.status.set("no live dir — type one above, or click Browse…")
            return

        # status.json counts as a publish file here: the recorder rewrites it on
        # every tick, and StopRecording writes one final done=true without
        # touching the frame files, so a status-only change must also redraw.
        stamp = {name: self._file_stamp(name)[1:] for name in
                 ("frame.ppm", "sprites.json", "chr.bin", "palette.json", "status.json")}
        changed = any(stamp[n] != self._seen.get(n) for n in stamp)
        self._seen = stamp

        status_path, st_ns, st_size = self._file_stamp("status.json")
        status = {}
        if st_ns is not None:
            try:
                status = json.loads((self.live_dir / "status.json").read_text())
            except (ValueError, OSError):
                status = {}

        # The ROM the slot now describes. The emulator's slot is one directory
        # reused by every session (ADR-0169 section 4), so this is the only
        # signal that the frames stopped being the same game's.
        rom = vl.rom_name(status)
        if rom != self._rom:
            self._rom = rom
            self.root.title(vl.window_title(rom))
            self._forget_frame_state()
            changed = True

        if st_ns is None or status.get("frame") is None:
            self._set_badge("IDLE")
            self.status.set(vl.waiting_text(self.live_dir))
            self.notice_var.set("")
            return
        if not changed and self._status_text is not None:
            self._refresh_status_strip()
            return

        state = self._read_once()
        self._status_text = None
        if state is None:
            self._set_badge("IDLE")
            self.status.set(vl.waiting_text(self.live_dir))
            return

        hd_pack_active = bool(status.get("hdPackActive"))
        sprites = state["sprites"]
        has_bg = state.get("background") is not None and state.get("nametables") is not None
        self.bg_filter_check.config(state="normal" if (sprites is not None and has_bg) else "disabled")
        self.sprite_meta.set(vl.format_reconstruction_meta(
            sprites, state.get("background") if has_bg else None))
        self.note_var.set(vl.reconstruction_note(sprites is not None, has_bg, hd_pack_active))

        self._status_text = vl.format_run_state(status)
        self._notice_text = " · ".join(vl.format_notices(status, sprites))
        self._set_badge(vl.run_badge(status))
        self._refresh_status_strip()
        self._draw(state)

    def _draw(self, state):
        scale = state["scale"] or 1
        w, h = state["width"], state["height"]

        # The composite is the recorder's own file - Tk decodes the PPM in C.
        # Kept unzoomed so a resize can re-zoom it without re-reading the file.
        try:
            self._composite_raw = tk.PhotoImage(file=str(state["ppm"]))
        except tk.TclError as e:
            self.status.set(f"cannot decode frame.ppm: {e}")
            return
        self._composite_native_wh = (w, h)
        self._redraw_composite_pane()

        # The reconstruction pane is rebuilt from data; a temporary native PPM
        # then gets zoomed to the composite geometry (nearest, integer - Tk does
        # it in C). Cached so the layer filter checkboxes and a resize can
        # redraw this pane alone, without waiting for the next poll to bring
        # fresh data.
        sprites, chr_bytes, colors = state.get("sprites"), state.get("chr"), state.get("colors")
        self._last_sprite_state = (sprites, chr_bytes, colors, w, h, scale)
        bg = state.get("background")
        nt = state.get("nametables")
        scroll = state.get("scanlineScroll")
        chr_bank = state.get("scanlineChrBank")
        chr_rom_full = state.get("chrfull")
        self._last_bg_state = (bg, nt, scroll, chr_bank, chr_rom_full) if bg is not None and nt is not None else None
        chrlatch, chrfull = state.get("chrlatch"), state.get("chrfull")
        self._last_chrlatch_state = (chrlatch, chrfull) if chrlatch is not None and chrfull is not None else None
        self._draw_sprite_pane()

    def _redraw_composite_pane(self):
        # Repaint the composite pane at the current display zoom - called on
        # every poll's fresh frame, and again on a window resize or a zoom
        # change.
        if self._composite_raw is None or self._composite_native_wh is None:
            return
        w, h = self._composite_native_wh
        self._display_zoom = self._compute_display_zoom(w, h)
        dz = self._display_zoom
        self.composite_meta.set(vl.format_composite_meta(w, h, geometry_scale(w, h), dz))
        self.zoom_readout.set(f"{dz}× (fit)" if self.fit_var.get() else f"{dz}×")
        self._composite_img = self._composite_raw.zoom(dz, dz) if dz > 1 else self._composite_raw
        self._composite_origin = self._centre_image(self.composite_canvas,
                                                    self._composite_img, "frame")
        self._draw_marks_current()

    def _draw_sprite_pane(self):
        if self._last_sprite_state is None:
            return
        sprites, chr_bytes, colors, w, h, scale = self._last_sprite_state
        if sprites is None or chr_bytes is None or colors is None:
            self.sprite_canvas.delete("all")
            return
        # CHR-latch mappers (MMC2/MMC4 — 2026-09-08 ADR-0169 update) need the
        # two layers built together in fetch order (build_planes_with_chr_latch
        # docstring); every other mapper keeps the simpler two-function path.
        if self._last_chrlatch_state is not None and self._last_bg_state is not None:
            chrlatch, chrfull = self._last_chrlatch_state
            # The latch path resolves CHR through chrfull by walking the frame
            # in fetch order (build_planes_with_chr_latch), so the bank trace
            # in _last_bg_state is irrelevant here - those slots are skipped.
            bg_dict, nametables, scanline_scroll, _chr_bank, _chr_rom_full = self._last_bg_state
            init_left, init_right = deduce_initial_chr_latch(chr_bytes, chrfull, chrlatch)
            bg_plane, bg_opaque, sp_plane, sp_behind, touched = build_planes_with_chr_latch(
                bg_dict if self.show_bg_var.get() else None, nametables, sprites,
                chrfull, chrlatch, init_left, init_right, scanline_scroll)
            if not self.show_front_var.get() or not self.show_behind_var.get():
                # The latch path draws every sprite as it fetches (the trigger
                # tiles have to be walked in fetch order regardless); honour a
                # layer checkbox by re-filtering after the fact instead.
                for i, (_y0, _tile, attr, _x) in enumerate(sprites["oam"]):
                    behind_attr = bool(attr & 0x20)
                    if (behind_attr and not self.show_behind_var.get()) or \
                            (not behind_attr and not self.show_front_var.get()):
                        touched[i] = False
                for cell in range(len(sp_plane)):
                    if sp_plane[cell]:
                        behind_attr = bool(sp_behind[cell])
                        if (behind_attr and not self.show_behind_var.get()) or \
                                (not behind_attr and not self.show_front_var.get()):
                            sp_plane[cell] = 0
        else:
            sp_plane, sp_behind, touched = build_sprite_planes(
                sprites, chr_bytes,
                show_front=self.show_front_var.get(),
                show_behind=self.show_behind_var.get())
            if self._last_bg_state is not None and self.show_bg_var.get():
                bg_dict, nametables, scanline_scroll, chr_bank, chr_rom_full = self._last_bg_state
                bg_plane, bg_opaque = build_background_plane(
                    bg_dict, nametables, chr_bytes, scanline_scroll,
                    scanline_chr_bank=chr_bank, chr_rom_full=chr_rom_full)
            else:
                bg_plane, bg_opaque = empty_background_plane()
        plane = compose_reconstruction(bg_plane, bg_opaque, sp_plane, sp_behind)
        ppm = make_palette_ppm(plane, sprites["palette"], colors)
        with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as f:
            f.write(ppm)
            path = f.name
        # Zoom straight from native (256x240) to the composite's displayed
        # size: the recorder's own scale, times the shared display zoom.
        total_zoom = scale * self._display_zoom
        try:
            pane = tk.PhotoImage(file=path)
            if total_zoom > 1:
                pane = pane.zoom(total_zoom, total_zoom)
        finally:
            Path(path).unlink(missing_ok=True)
        self._pane_img = pane
        self._centre_image(self.sprite_canvas, pane, "frame")

        self._last_mark_data = (sprites, touched)
        self._draw_marks_current()

    def _redraw_sprite_pane(self):
        # Repaint just the reconstruction pane after a layer filter flip, from
        # the last poll's data — same idea as _draw_marks_current.
        self._draw_sprite_pane()

    def _draw_marks_current(self):
        # (Re)draw the sprite-bounds overlay from the last sprite data, at the
        # current zoom and the image's centred origin — shared by a poll's
        # fresh frame, a resize, a zoom change and the "sprite boxes" toggle.
        self.composite_canvas.delete("spritemark")
        if self._last_mark_data is None or not self.mark_var.get() \
                or self._composite_native_wh is None or self._composite_img is None:
            return
        sprites, touched = self._last_mark_data
        w, h = self._composite_native_wh
        ox, oy = getattr(self, "_composite_origin", (0, 0))
        fx = (w * self._display_zoom) / NATIVE_W
        fy = (h * self._display_zoom) / NATIVE_H
        for x, y, bw, bh in sprite_boxes(sprites, touched):
            self.composite_canvas.create_rectangle(
                ox + x * fx, oy + y * fy, ox + (x + bw) * fx, oy + (y + bh) * fy,
                outline="#40c0ff", width=1, tags="spritemark")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="MesenCE live recording viewer (ADR-0169) — watch the "
                    "emulator's live recording, or a headless run, without "
                    "touching the run (read-only)")
    ap.add_argument("live_dir", nargs="?", default=None,
                    help="a <prefix>-live/ folder to watch; defaults to the "
                         "emulator's LiveRecording convention slot")
    args = ap.parse_args(argv)
    live_dir = Path(args.live_dir) if args.live_dir else emulator_live_dir()
    root = tk.Tk()
    root.geometry("1100x780")
    RecordViewerApp(root, live_dir)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
