#!/usr/bin/env python3
"""Generates synthetic test ROMs (clean-room, no third-party bytes at all)
to validate the GB/SMS HD Pack Builder (F2): each ROM uploads a few known
tiles, known palettes and a pair of sprites, then locks into an infinite loop.

Usage: python3 scripts/gen_hdpack_test_roms.py <output-dir>
Generates: test_dmg.gb, test_cgb.gbc, test_sms.sms

The GB headers do not include the Nintendo logo (the open-source SameBoy
boot ROMs embedded in Mesen do not require it) — keeps the repository clean.
"""
import sys
from pathlib import Path


def assemble(items, org):
    """Mini 2-pass assembler: items are bytes(), ('label', name) or
    ('rel8', opcode_bytes, label) for relative jumps / ('addr16le', label)."""
    labels = {}
    pos = org
    for it in items:
        if isinstance(it, tuple) and it[0] == "label":
            labels[it[1]] = pos
        elif isinstance(it, tuple) and it[0] == "rel8":
            pos += len(it[1]) + 1
        elif isinstance(it, tuple) and it[0] == "addr16le":
            pos += 2
        else:
            pos += len(it)

    out = bytearray()
    pos = org
    for it in items:
        if isinstance(it, tuple) and it[0] == "label":
            continue
        if isinstance(it, tuple) and it[0] == "rel8":
            out += it[1]
            pos += len(it[1]) + 1
            rel = labels[it[2]] - pos
            assert -128 <= rel <= 127, f"relative jump out of range: {it[2]}"
            out.append(rel & 0xFF)
        elif isinstance(it, tuple) and it[0] == "addr16le":
            addr = labels[it[1]]
            out += bytes([addr & 0xFF, addr >> 8])
            pos += 2
        else:
            out += it
            pos += len(it)
    return out


# ---------------------------------------------------------------- Game Boy

GB_TILES = bytes(16) + bytes(
    # tile 1: varied 2bpp rows (uses all 4 colors)
    [0xFF, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xF0, 0x0F,
     0xCC, 0x33, 0xAA, 0x55, 0x0F, 0xF0, 0x3C, 0xC3]
) + bytes(
    # tile 2: another pattern
    [0x81, 0x7E, 0x42, 0x3C, 0x24, 0x18, 0x18, 0x24,
     0x18, 0x24, 0x24, 0x18, 0x42, 0x3C, 0x81, 0x7E]
)

CGB_BG_PAL = bytes([0xFF, 0x7F, 0x1F, 0x00, 0xE0, 0x03, 0x00, 0x7C])   # white, red, green, blue
CGB_OBJ_PAL = bytes([0x00, 0x00, 0x1F, 0x7C, 0xFF, 0x03, 0xE0, 0x7F])  # (color 0 is transparent)


def gb_program(cgb):
    ldh = lambda reg, val: bytes([0x3E, val, 0xE0, reg])  # ld a,v ; ldh (reg),a
    code = [
        bytes([0xF3]),                       # di
        ("label", "wait_vbl"),
        bytes([0xF0, 0x44, 0xFE, 0x90]),     # ldh a,(44) ; cp 0x90
        ("rel8", bytes([0x38]), "wait_vbl"), # jr c,wait_vbl
        bytes([0xAF, 0xE0, 0x40]),           # xor a ; ldh (40),a - LCD off
        ldh(0x47, 0xE4),                     # BGP
        ldh(0x48, 0xD2),                     # OBP0
        ldh(0x49, 0x1B),                     # OBP1
        # copy 48 bytes of tiles to 0x8000
        bytes([0x21]), ("addr16le", "tiles"),
        bytes([0x11, 0x00, 0x80, 0x01, 0x30, 0x00]),
        ("label", "copy"),
        bytes([0x2A, 0x12, 0x13, 0x0B, 0x78, 0xB1]),
        ("rel8", bytes([0x20]), "copy"),
        # clear the tilemap 0x9800-0x9BFF
        bytes([0x21, 0x00, 0x98, 0x01, 0x00, 0x04]),
        ("label", "clr_map"),
        bytes([0xAF, 0x22, 0x0B, 0x78, 0xB1]),
        ("rel8", bytes([0x20]), "clr_map"),
        # map entries: tile 1 and tile 2
        bytes([0x21, 0x00, 0x98, 0x36, 0x01, 0x23, 0x36, 0x02]),
        # clear the OAM
        bytes([0x21, 0x00, 0xFE, 0x06, 0xA0]),
        ("label", "clr_oam"),
        bytes([0xAF, 0x22, 0x05]),
        ("rel8", bytes([0x20]), "clr_oam"),
        # sprite 0: Y=0x50 X=0x50 tile=2 attr=0x00 / sprite 1: Y=0x50 X=0x60 tile=1 attr=0x10 (OBP1)
        bytes([0x21, 0x00, 0xFE,
               0x36, 0x50, 0x23, 0x36, 0x50, 0x23, 0x36, 0x02, 0x23, 0x36, 0x00, 0x23,
               0x36, 0x50, 0x23, 0x36, 0x60, 0x23, 0x36, 0x01, 0x23, 0x36, 0x10]),
    ]
    if cgb:
        code += [
            # BG palette 0 via BCPS/BCPD
            ldh(0x68, 0x80),
            bytes([0x21]), ("addr16le", "bgpal"),
            bytes([0x06, 0x08]),
            ("label", "bgp_cp"),
            bytes([0x2A, 0xE0, 0x69, 0x05]),
            ("rel8", bytes([0x20]), "bgp_cp"),
            # OBJ palette 0 via OCPS/OCPD
            ldh(0x6A, 0x80),
            bytes([0x21]), ("addr16le", "objpal"),
            bytes([0x06, 0x08]),
            ("label", "obp_cp"),
            bytes([0x2A, 0xE0, 0x6B, 0x05]),
            ("rel8", bytes([0x20]), "obp_cp"),
            # clear the attribute map (VRAM bank 1)
            ldh(0x4F, 0x01),
            bytes([0x21, 0x00, 0x98, 0x01, 0x00, 0x04]),
            ("label", "clr_attr"),
            bytes([0xAF, 0x22, 0x0B, 0x78, 0xB1]),
            ("rel8", bytes([0x20]), "clr_attr"),
            ldh(0x4F, 0x00),
        ]
    code += [
        ldh(0x40, 0x93),                     # LCD on, BG on, OBJ on, tiles at 0x8000
        ("label", "halt"),
        ("rel8", bytes([0x18]), "halt"),     # jr halt
        ("label", "tiles"),
        GB_TILES,
        ("label", "bgpal"),
        CGB_BG_PAL,
        ("label", "objpal"),
        CGB_OBJ_PAL,
    ]
    return assemble(code, 0x150)


def make_gb_rom(cgb):
    rom = bytearray(0x8000)
    rom[0x100:0x104] = bytes([0x00, 0xC3, 0x50, 0x01])  # nop ; jp 0x150
    title = b"HDPACKTEST"
    rom[0x134:0x134 + len(title)] = title
    if cgb:
        rom[0x143] = 0xC0
    # cart type 0 (ROM only), 32KB, no RAM - all already zero
    checksum = 0
    for addr in range(0x134, 0x14D):
        checksum = (checksum - rom[addr] - 1) & 0xFF
    rom[0x14D] = checksum
    prog = gb_program(cgb)
    rom[0x150:0x150 + len(prog)] = prog
    return rom


# ---------------------------------------------------------------- SMS

SMS_TILES = bytes(32) + bytes(
    # tile 1: 8 rows of 4 bitplanes with varied patterns
    [0xF0, 0xCC, 0xAA, 0x00] * 4 + [0x0F, 0x33, 0x55, 0x00] * 4
) + bytes(
    # tile 2: uses the high bitplane (colors 8-15)
    [0x3C, 0x66, 0x00, 0xFF] * 4 + [0xC3, 0x99, 0xFF, 0xFF] * 4
)

SMS_CRAM = bytes([(i * 2 + 1) & 0x3F for i in range(32)])  # 32 distinct RGB222 entries


def sms_program():
    def setreg(reg, val):
        return bytes([0x3E, val, 0xD3, 0xBF, 0x3E, 0x80 | reg, 0xD3, 0xBF])

    def setaddr(lo, hi):
        return bytes([0x3E, lo, 0xD3, 0xBF, 0x3E, hi, 0xD3, 0xBF])

    def otir(label, count):
        return [
            bytes([0x21]), ("addr16le", label),
            bytes([0x06, count, 0x0E, 0xBE, 0xED, 0xB3]),  # ld b,n ; ld c,0xBE ; otir
        ]

    code = [
        bytes([0xF3, 0x31, 0xF0, 0xDF]),  # di ; ld sp,0xDFF0
        setreg(0, 0x06),                  # mode 4 (M4|M2)
        setreg(1, 0x00),                  # display off during setup
        setreg(2, 0xFF),                  # nametable 0x3800
        setreg(5, 0xFF),                  # sprite table 0x3F00
        setreg(6, 0xFF),                  # sprite patterns 0x2000
        setreg(7, 0x00),
        setreg(8, 0x00),
        setreg(9, 0x00),
        setreg(10, 0xFF),
        # full CRAM (32 entries)
        setaddr(0x00, 0xC0),
        *otir("cram", 32),
        # tiles 0-2 at 0x0000
        setaddr(0x00, 0x40),
        *otir("tiles", 96),
        # tile 2 also at 0x2000 (sprite region) as tile index 0
        setaddr(0x00, 0x60),
        *otir("tile2", 32),
        # clear the nametable 0x3800-0x3EFF
        setaddr(0x00, 0x78),
        bytes([0x01, 0x00, 0x07]),        # ld bc,0x700
        ("label", "nt_clr"),
        bytes([0xAF, 0xD3, 0xBE, 0x0B, 0x78, 0xB1]),
        ("rel8", bytes([0x20]), "nt_clr"),
        # entries: tile 1 (low palette) and tile 2 (bit 11 = high palette)
        setaddr(0x00, 0x78),
        bytes([0x3E, 0x01, 0xD3, 0xBE, 0xAF, 0xD3, 0xBE,
               0x3E, 0x02, 0xD3, 0xBE, 0x3E, 0x08, 0xD3, 0xBE]),
        # sprites: sprite 0's Y = 0x50, terminator 0xD0
        setaddr(0x00, 0x7F),
        bytes([0x3E, 0x50, 0xD3, 0xBE, 0x3E, 0xD0, 0xD3, 0xBE]),
        # sprite 0's X/index at 0x3F80: X=0x50, tile=0 (region 0x2000)
        setaddr(0x80, 0x7F),
        bytes([0x3E, 0x50, 0xD3, 0xBE, 0xAF, 0xD3, 0xBE]),
        setreg(1, 0x40),                  # display on
        ("label", "halt"),
        ("rel8", bytes([0x18]), "halt"),
        ("label", "cram"),
        SMS_CRAM,
        ("label", "tiles"),
        SMS_TILES,
        ("label", "tile2"),
        SMS_TILES[64:96],
    ]
    return assemble(code, 0x0000)


def make_sms_rom():
    rom = bytearray(0x8000)
    prog = sms_program()
    rom[0:len(prog)] = prog
    return rom


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "test_dmg.gb").write_bytes(make_gb_rom(cgb=False))
    (out / "test_cgb.gbc").write_bytes(make_gb_rom(cgb=True))
    (out / "test_sms.sms").write_bytes(make_sms_rom())
    print(f"test ROMs generated in {out}")


if __name__ == "__main__":
    main()
