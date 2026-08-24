#!/usr/bin/env python3
"""Generates a minimal Game Boy test ROM that plays a looping melody on
square channel 1 plus a noise hit per note - enough APU traffic to exercise
the GB legs of the MIDI/VGM exporters (F1) without any commercial ROM.

Usage: make_gb_test_rom.py <output.gb>
"""
import sys

NINTENDO_LOGO = bytes.fromhex(
    "CEED6666CC0D000B03730083000C000D0008111F8889000EDCCC6EE6"
    "DDDDD999BBBB67636E0EECCCDDDC999FBBB9333E")

def note_x(freq_hz):
    """NR13/NR14 11-bit period for a square-channel frequency."""
    return 2048 - round(131072 / freq_hz)

MELODY_HZ = [261.63, 329.63, 392.00, 523.25,  # C4 E4 G4 C5
             493.88, 392.00, 440.00, 349.23,  # B4 G4 A4 F4
             392.00, 329.63, 349.23, 293.66,  # G4 E4 F4 D4
             329.63, 261.63]                  # E4 C4

rom = bytearray(0x8000)

# Entry point: nop; jp $0150
rom[0x100:0x104] = bytes([0x00, 0xC3, 0x50, 0x01])
rom[0x104:0x134] = NINTENDO_LOGO
rom[0x134:0x13E] = b"F1TESTTONE"
rom[0x14A] = 0x01  # destination: non-Japan

code = bytes([
    0xF3,              # di
    0x31, 0xFE, 0xFF,  # ld sp,$FFFE
    0x3E, 0x80,        # ld a,$80
    0xE0, 0x26,        #   ldh ($26),a  NR52: APU on
    0x3E, 0xFF,        # ld a,$FF
    0xE0, 0x25,        #   ldh ($25),a  NR51: all channels to both sides
    0x3E, 0x77,        # ld a,$77
    0xE0, 0x24,        #   ldh ($24),a  NR50: max master volume
    # restart: ($0160)
    0x21, 0xA0, 0x01,  # ld hl,$01A0   note table
    # next_note: ($0163)
    0x2A,              # ld a,(hl+)    period low byte
    0x47,              # ld b,a
    0x2A,              # ld a,(hl+)    period high bits ($FF = wrap)
    0xFE, 0xFF,        # cp $FF
    0x28, 0xF6,        # jr z,restart
    0x4F,              # ld c,a
    0x3E, 0x80,        # ld a,$80
    0xE0, 0x11,        #   ldh ($11),a  NR11: 50% duty
    0x3E, 0xF0,        # ld a,$F0
    0xE0, 0x12,        #   ldh ($12),a  NR12: volume 15, no envelope
    0x78,              # ld a,b
    0xE0, 0x13,        #   ldh ($13),a  NR13: period low
    0x79,              # ld a,c
    0xF6, 0x80,        # or $80        trigger bit
    0xE0, 0x14,        #   ldh ($14),a  NR14: trigger + period high
    0x3E, 0xF1,        # ld a,$F1
    0xE0, 0x21,        #   ldh ($21),a  NR42: noise vol 15, fast decay
    0x3E, 0x55,        # ld a,$55
    0xE0, 0x22,        #   ldh ($22),a  NR43: mid shift rate
    0x3E, 0x80,        # ld a,$80
    0xE0, 0x23,        #   ldh ($23),a  NR44: trigger noise
    # ~0.26s busy-wait (256 x 256 x 16 clocks at 4.19MHz)
    0x16, 0x00,        # ld d,0        (256 outer)
    # d1: ($0189)
    0x1E, 0x00,        # ld e,0        (256 inner)
    # d2: ($018B)
    0x1D,              # dec e
    0x20, 0xFD,        # jr nz,d2
    0x15,              # dec d
    0x20, 0xF8,        # jr nz,d1
    0x18, 0xD0,        # jr next_note
])
rom[0x150:0x150 + len(code)] = code

table = bytearray()
for hz in MELODY_HZ:
    x = note_x(hz)
    table += bytes([x & 0xFF, (x >> 8) & 0x07])
table += bytes([0x00, 0xFF])  # end marker
rom[0x1A0:0x1A0 + len(table)] = table

# Header checksum over $0134-$014C
chk = 0
for b in rom[0x134:0x14D]:
    chk = (chk - b - 1) & 0xFF
rom[0x14D] = chk

# Global checksum (sum of all bytes except its own two)
total = (sum(rom) - rom[0x14E] - rom[0x14F]) & 0xFFFF
rom[0x14E] = total >> 8
rom[0x14F] = total & 0xFF

out = sys.argv[1] if len(sys.argv) > 1 else "f1-test-tone.gb"
with open(out, "wb") as f:
    f.write(rom)
print(f"gerado: {out} ({len(rom)} bytes, checksum de header {chk:#04x})")
