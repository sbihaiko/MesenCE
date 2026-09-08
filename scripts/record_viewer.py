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
    status.json      progress / done

By convention this tool attaches to the emulator's own slot, so there is
nothing to type to watch a live session:

    python3 scripts/record_viewer.py

Pass a path to watch a headless run instead (or type one in the Live dir box
and click Attach):

    python3 scripts/record_viewer.py runs/<rom>-<stamp>-live/

Either way this tool only polls the directory and draws what it finds; it never
writes a byte into it, and it never launches a recording — start and stop live
recording from the emulator, start headless runs from a terminal.

The bottom pane is a *reconstruction* of the frame, not a second capture: OAM
entries are expanded through the NES 8x8/8x16 rules of NesPpu::LoadSprite and
the background tiles are re-laid out through the captured loopy scroll, then
both are multiplexed the way the 2C02's priority logic does (front sprites over
everything; behind-background sprites only through a backdrop pixel). So it
applies what a single end-of-frame capture can prove — palette RAM, OAM, pattern
tables, nametables, scroll, the mask bits — and ignores what it cannot see:
the 8-sprites-per-scanline limit and any mid-frame scroll split. Recordings from
before the background capture land on the wire format show only sprites over the
backdrop color, the way this tool always did. The pane may still disagree with
the composed frame above it in those spots; the layer checkboxes exist to hide a
layer and see what the others would look like on their own.

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
from tkinter import ttk

# The NES sprite plane, in its own native pixels (the recorder's frame.ppm may
# be scaled, e.g. 2x -> 512x480; geometry_scale() recovers the factor).
NATIVE_W = 256
NATIVE_H = 240

# An OAM y >= 0xF0 puts the sprite's rows entirely below the last visible
# scanline (it wrapped off the bottom), so the PPU never shows it — skip it
# the same way the hardware does.
HIDDEN_SPRITE_Y = 0xF0

# Caption prefix for the reconstruction pane once the background layer is on the
# wire (2026-09-08 ADR-0169 "capture every layer"). Everything an end-of-frame
# capture can prove is applied - priority, the mask bits, palette - so the pane
# is a real multiplex of both layers; only the per-scanline limits a single
# capture cannot see are left out and named.
RECONSTRUCTION_CAVEAT = (
    "rebuilt from OAM + nametables — same priority as the PPU (front sprites, "
    "behind sprites only through a backdrop pixel, mask bits honoured), but it "
    "cannot see a frame's 8-sprites-per-scanline overflow or a mid-frame scroll "
    "split, so a sprite here may still differ from the frame above")

# Older recordings (and non-background captures) show sprites over the backdrop
# color alone; name that so it reads as "no background data", not as an error.
SPRITES_ONLY_CAVEAT = (
    "rebuilt from OAM only (this recording predates the background capture) — "
    "sprites drawn over the backdrop color, no priority to multiplex")


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


def build_planes_with_chr_latch(bg, nametables, sprites, chr_full, latch, initial_left, initial_right):
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
    clip_left_bg = bg["leftColumnClip"] if bg_enabled else False

    for row_y in range(NATIVE_H):
        # ---- this row's background tiles, left to right (fetched first — see
        # this function's docstring on fetch order) ----
        if bg_enabled:
            world_y = scroll_y + row_y
            if world_y >= 480:
                world_y -= 480
            v_sel, y_in_page = divmod(world_y, 240)
            row_in_nt, fine_y = divmod(y_in_page, 8)
            page_base = v_sel << 11
            row_base = row_in_nt * 32
            attr_row = (row_in_nt >> 2) * 8
            quad_y = (row_in_nt & 2) << 1
            out_row = row_y * NATIVE_W
            p = 0
            wx = scroll_x
            while p < NATIVE_W:
                col_world = (wx >> 3) & 0x3F
                h_sel = col_world >> 5
                col_in_nt = col_world & 0x1F
                tile_index = nametables[page_base + h_sel * 0x400 + row_base + col_in_nt]
                attr = nametables[page_base + h_sel * 0x400 + 0x3C0 + attr_row + (col_in_nt >> 2)]
                subpal = ((attr >> (quad_y | (col_in_nt & 2))) & 3) << 2
                low, high = fetch(bg_half, tile_index, fine_y)
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


def build_background_plane(bg, nametables, chr_bytes):
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

    Layout uses loopy "t" (bg['tmpScroll'], the scroll the game wrote — at an
    end-of-frame boundary loopy "v" has already scanned the whole frame, so t is
    the only stable base) plus fine X: t's coarse X (bits 0-4) and horizontal
    page bit (10) and coarse Y (5-9), vertical page bit (11) and fine Y (12-14)
    place the screen's top-left in a 512x480 2x2-nametable world."""
    plane = bytearray(NATIVE_W * NATIVE_H)
    opaque = bytearray(NATIVE_W * NATIVE_H)
    if not bg["enabled"]:
        return plane, opaque

    t = bg["tmpScroll"]
    fine_x0 = bg["fineScrollX"]
    scroll_x = ((t >> 10) & 1) * 256 + (t & 0x1F) * 8 + fine_x0
    scroll_y = ((t >> 11) & 1) * 240 + ((t >> 5) & 0x1F) * 8 + ((t >> 12) & 7)
    pattern = bg["patternAddr"]
    nt = nametables

    # World space is 512x480 (2x2 nametable pages), but a page is 256x240 -
    # 32 tile columns by *30* tile rows, not 32: a nametable's bytes for tile
    # rows 30-31 hold no tile data (IncVerticalScrolling wraps coarse Y at 29,
    # not 31). scroll_y/world_y above are already built on that 240-per-page
    # basis, so page/row-in-page here must come from a divmod by 240/30, not a
    # bit shift assuming 256/32 - mixing the two silently reads the wrong page.
    for py in range(NATIVE_H):
        world_y = scroll_y + py
        if world_y >= 480:
            world_y -= 480  # a 256-tall viewport never crosses more than one edge
        v_sel, y_in_page = divmod(world_y, 240)
        row_in_nt, fine_y = divmod(y_in_page, 8)
        page_base = (v_sel << 11)  # vertical select is address bit 11
        row_base = row_in_nt * 32
        attr_row = (row_in_nt >> 2) * 8
        quad_y = (row_in_nt & 2) << 1
        out_row = py * NATIVE_W
        p = 0
        wx = scroll_x
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
            ta = pattern + (tile_index << 4) + fine_y
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
    POLL_MS = 100

    def __init__(self, root: tk.Tk, live_dir: Path):
        self.root = root
        self.live_dir = live_dir
        root.title("MesenCE — live recording viewer (ADR-0169)")
        self._imgs = []          # keep PhotoImages alive (Tk drops them on GC)
        self._seen = {}          # {path: (mtime_ns, size)} of the last draw
        self._status_text = None
        self._last_mark_data = None  # (sprites, touched) of the last draw
        self._last_sprite_state = None  # (sprites, chr, colors, w, h, scale) of the last draw
        self._last_bg_state = None   # (bg dict, nametables bytes) of the last draw, or None
        self._last_chrlatch_state = None  # (chrlatch dict, chrfull bytes) of the last draw, or None
        self._composite_raw = None      # unzoomed PhotoImage decoded from frame.ppm
        self._composite_native_wh = None  # (w, h) of frame.ppm, before display zoom
        self._display_zoom = 1          # shared zoom applied on top of the recorder's own scale, to fill the window
        self._resize_job = None

        # ---- top bar: the live directory ------------------------------------
        # Pre-filled with the emulator's convention slot; type another path to
        # watch a headless run and click Attach.
        top = ttk.Frame(root, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Live dir:").pack(side="left")
        self.live_dir_var = tk.StringVar(value=str(live_dir))
        self.live_dir_entry = ttk.Entry(top, textvariable=self.live_dir_var, width=56)
        self.live_dir_entry.pack(side="left", padx=(4, 4))
        self.attach_btn = ttk.Button(top, text="Attach", command=self._attach)
        self.attach_btn.pack(side="left")
        ttk.Button(top, text="Poll now", command=self._poll).pack(side="right")
        self.status = tk.StringVar(value="starting…")
        ttk.Label(root, textvariable=self.status, foreground="#555",
                  wraplength=1400).pack(fill="x", padx=6)

        # ---- the two panes: composite | reconstruction ---------------------
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=6, pady=6)

        self.left = left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self.mark_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="mark sprite bounds on the composite",
                        variable=self.mark_var, command=self._redraw_marks).pack(anchor="w")
        self.composite_canvas = tk.Canvas(left, background="#000",
                                          highlightthickness=0)
        self.composite_canvas.pack(expand=True)
        self.composite_caption = tk.StringVar()
        ttk.Label(left, textvariable=self.composite_caption, foreground="#888",
                  wraplength=520).pack(anchor="w", pady=(2, 0))

        self.right = right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        filters = ttk.Frame(right)
        filters.pack(anchor="w")
        self.show_bg_var = tk.BooleanVar(value=True)
        self.bg_filter_check = ttk.Checkbutton(filters, text="background",
                                               variable=self.show_bg_var,
                                               command=self._redraw_sprite_pane)
        self.bg_filter_check.pack(side="left")
        self.show_front_var = tk.BooleanVar(value=True)
        self.show_behind_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(filters, text="front sprites", variable=self.show_front_var,
                        command=self._redraw_sprite_pane).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(filters, text="behind-background sprites",
                        variable=self.show_behind_var,
                        command=self._redraw_sprite_pane).pack(side="left", padx=(8, 0))
        self.sprite_canvas = tk.Canvas(right, background="#000",
                                       highlightthickness=0)
        self.sprite_canvas.pack(expand=True)
        self.sprite_caption = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.sprite_caption, foreground="#888",
                  wraplength=520).pack(anchor="w", pady=(2, 0))

        # Both panes share one display zoom (recomputed from the available
        # frame size), so a bigger window shows bigger pixels instead of
        # dead space around a NES-native-sized image.
        left.bind("<Configure>", self._schedule_resize)
        right.bind("<Configure>", self._schedule_resize)

        self.root.after(self.POLL_MS, self._poll)

    # ---- fill-the-window display zoom --------------------------------------

    MAX_DISPLAY_ZOOM = 4

    def _schedule_resize(self, event=None):
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(80, self._on_resize)

    def _on_resize(self):
        self._resize_job = None
        self._redraw_composite_pane()
        self._redraw_sprite_pane()

    def _compute_display_zoom(self, w, h):
        """Integer zoom (capped) that fits w x h into the left pane's current
        size, so the two viewports grow with the window instead of sitting at
        a fixed, often tiny, native/recorder size."""
        self.root.update_idletasks()
        avail_w = self.left.winfo_width() or w
        avail_h = max(self.left.winfo_height() - 60, h)  # minus the checkbox/caption rows
        if w <= 0 or h <= 0:
            return 1
        return max(1, min(avail_w // w, avail_h // h, self.MAX_DISPLAY_ZOOM))

    # ---- manual attach ----------------------------------------------------

    def _attach(self):
        """Point the viewer at a live directory the emulator (convention slot)
        or a terminal-launched headless run is publishing into."""
        text = self.live_dir_var.get().strip()
        if not text:
            return
        self.live_dir = Path(text)
        self._seen = {}
        self._status_text = None
        self._poll()

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
        # CHR-latch extension (2026-09-08 ADR-0169 update): chrlatch.json and
        # chrfull.bin are written together, only for a mapper with the latch
        # (BaseMapper::HasChrBankLatch — MMC2/MMC4). Either being absent means
        # this run's mapper has none; the flat chr.bin path above is correct
        # for it and every other mapper.
        latch_path, latch_ns, _latch_size = self._file_stamp("chrlatch.json")
        if latch_ns is not None:
            try:
                out["chrlatch"] = parse_chrlatch_json((self.live_dir / "chrlatch.json").read_text())
                out["chrfull"] = (self.live_dir / "chrfull.bin").read_bytes()
            except (ValueError, OSError):
                out["chrlatch"] = None
                out["chrfull"] = None
        return out

    def _poll(self):
        try:
            self._poll_once()
        except Exception as e:  # keep the poll loop alive on a bad file
            self.status.set(f"cannot read live data: {e}")
        self.root.after(self.POLL_MS, self._poll)

    def _poll_once(self):
        if self.live_dir is None:
            self.status.set("no live dir — type one above and click Attach")
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

        if st_ns is None or status.get("frame") is None:
            self.status.set("no run published yet — start Live Recording in the "
                             "emulator (Tools menu), or Attach a headless "
                             f"<prefix>-live/ dir instead of {self.live_dir}")
            return
        if not changed and self._status_text is not None:
            self.status.set(self._status_text)
            return

        state = self._read_once()
        self._status_text = None
        if state is None:
            self.status.set(f"no frames published yet — waiting for {self.live_dir}")
            return

        frame = status.get("frame", "?")
        target = status.get("targetFrames", 0)
        done = bool(status.get("done"))
        wall = status.get("elapsedWallSec", 0)
        if done:
            tail = "stopped"
        elif target:
            tail = f"of {target}"  # a scripted run a human launched at a terminal
        else:
            tail = "live"  # interactive: no target - frames run until stopped
        state_text = f"frame {frame} {tail} · wall {wall}s"
        if state["sprites"] is not None:
            sp = state["sprites"]
            state_text += f" · capture {sp['captureFrame']}"
            if not sp["spritesEnabled"]:
                state_text += " · sprites disabled on this frame (OAM may be stale)"
            has_bg = state.get("background") is not None and state.get("nametables") is not None
            caveat = RECONSTRUCTION_CAVEAT if has_bg else SPRITES_ONLY_CAVEAT
            if has_bg:
                self.bg_filter_check.config(state="normal")
                bg = state["background"]
            else:
                self.bg_filter_check.config(state="disabled")
                bg = None
            det = " · " + ("8×16" if sp["largeSprites"] else "8×8")
            det += f" · sprite ${sp['patternAddr']:04X}"
            if bg is not None:
                det += f" · bg ${bg['patternAddr']:04X}"
                if not bg["enabled"]:
                    det += " · bg off this frame"
                if bg["leftColumnClip"]:
                    det += " · bg left clip"
            if sp["leftColumnClip"]:
                det += " · sprite left clip"
            self.sprite_caption.set(caveat + det)
        else:
            self.bg_filter_check.config(state="disabled")
            self.sprite_caption.set("no sprite layer published (this is not a NES run, or sprites were off)")

        self.status.set(state_text)
        self._status_text = state_text
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
        self.composite_caption.set(
            f"composite — as the emulator rendered it ({w}×{h}, {scale}× native)")
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
        self._last_bg_state = (bg, nt) if bg is not None and nt is not None else None
        chrlatch, chrfull = state.get("chrlatch"), state.get("chrfull")
        self._last_chrlatch_state = (chrlatch, chrfull) if chrlatch is not None and chrfull is not None else None
        self._draw_sprite_pane()

    def _redraw_composite_pane(self):
        # Repaint the composite pane at the current display zoom - called on
        # every poll's fresh frame, and again on a window resize.
        if self._composite_raw is None or self._composite_native_wh is None:
            return
        w, h = self._composite_native_wh
        self._display_zoom = self._compute_display_zoom(w, h)
        dz = self._display_zoom
        composite = self._composite_raw.zoom(dz, dz) if dz > 1 else self._composite_raw
        self._imgs.append(composite)
        self.composite_canvas.config(width=w * dz, height=h * dz)
        self.composite_canvas.delete("frame")
        self.composite_canvas.create_image(0, 0, image=composite, anchor="nw", tags="frame")
        self._draw_marks_current()

    def _draw_sprite_pane(self):
        if self._last_sprite_state is None:
            return
        sprites, chr_bytes, colors, w, h, scale = self._last_sprite_state
        if sprites is None or chr_bytes is None or colors is None:
            self.sprite_canvas.config(width=256, height=240)
            self.sprite_canvas.delete("all")
            return
        # CHR-latch mappers (MMC2/MMC4 — 2026-09-08 ADR-0169 update) need the
        # two layers built together in fetch order (build_planes_with_chr_latch
        # docstring); every other mapper keeps the simpler two-function path.
        if self._last_chrlatch_state is not None and self._last_bg_state is not None:
            chrlatch, chrfull = self._last_chrlatch_state
            bg_dict, nametables = self._last_bg_state
            init_left, init_right = deduce_initial_chr_latch(chr_bytes, chrfull, chrlatch)
            bg_plane, bg_opaque, sp_plane, sp_behind, touched = build_planes_with_chr_latch(
                bg_dict if self.show_bg_var.get() else None, nametables, sprites,
                chrfull, chrlatch, init_left, init_right)
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
                bg_dict, nametables = self._last_bg_state
                bg_plane, bg_opaque = build_background_plane(bg_dict, nametables, chr_bytes)
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
        self._imgs.append(pane)
        self.sprite_canvas.config(width=w * self._display_zoom, height=h * self._display_zoom)
        self.sprite_canvas.delete("all")
        self.sprite_canvas.create_image(0, 0, image=pane, anchor="nw")

        self._last_mark_data = (sprites, touched)
        self._draw_marks_current()

    def _redraw_sprite_pane(self):
        # Repaint just the reconstruction pane after a layer filter flip, from
        # the last poll's data — same idea as _redraw_marks.
        self._draw_sprite_pane()

    def _draw_marks(self, sprites, touched, fx, fy):
        self.composite_canvas.delete("spritemark")
        for x, y, bw, bh in sprite_boxes(sprites, touched):
            self.composite_canvas.create_rectangle(
                x * fx, y * fy, (x + bw) * fx, (y + bh) * fy,
                outline="#40c0ff", width=1, tags="spritemark")

    def _draw_marks_current(self):
        # (Re)draw the overlay from the last sprite data, at the current
        # display zoom — shared by a poll's fresh frame, a resize, and the
        # "mark sprite bounds" checkbox.
        if self._last_mark_data is None or not self.mark_var.get() \
                or self._composite_native_wh is None:
            self.composite_canvas.delete("spritemark")
            return
        sprites, touched = self._last_mark_data
        w, h = self._composite_native_wh
        fx, fy = (w * self._display_zoom) / NATIVE_W, (h * self._display_zoom) / NATIVE_H
        self._draw_marks(sprites, touched, fx, fy)

    def _redraw_marks(self):
        # Repaint just the overlay after a checkbox flip, from the last draw.
        self._draw_marks_current()


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
    RecordViewerApp(root, live_dir)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
