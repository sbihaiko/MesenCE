#!/usr/bin/env python3
"""Generates a minimal, fully synthetic NROM (mapper 0) .nes ROM.

No copyrighted game data of any kind — every byte is either a fixed iNES
header field or a hand-picked 6502 opcode. Used to drive the real C++ core
(HdPackLoader / MepPackManager) against a submitted HD/MEP pack's hires.txt
in CI, where a real ROM can never be used. HdPackLoader::ProcessBackgroundTag
and ProcessConditionTag only parse pack file bytes and 6502-independent
condition tokens — they never read PRG/CHR content — so any loadable iNES
file is enough to exercise that validation path; the game logic itself is
irrelevant and deliberately does nothing (an infinite JMP-to-self at the
reset vector).

Usage: python3 scripts/gen_synthetic_nrom.py <output.nes>
"""
import sys
from pathlib import Path

PRG_SIZE = 32 * 1024  # NROM-256: $8000-$FFFF maps directly, no mirroring math
CHR_SIZE = 8 * 1024


def build_rom() -> bytes:
    header = bytearray(16)
    header[0:4] = b"NES\x1a"
    header[4] = PRG_SIZE // 16384  # PRG-ROM size, 16KB units
    header[5] = CHR_SIZE // 8192  # CHR-ROM size, 8KB units
    header[6] = 0x00  # mapper low nibble 0, horizontal mirroring, no battery/trainer
    header[7] = 0x00  # mapper high nibble 0 -> mapper 0 (NROM)
    # bytes 8-15 stay zero (iNES 1.0, no NES 2.0 flags needed)

    prg = bytearray(b"\xEA" * PRG_SIZE)  # NOP-filled
    prg[0x0000:0x0003] = bytes([0x4C, 0x00, 0x80])  # JMP $8000 (infinite self-loop)
    prg[0x0003:0x0004] = bytes([0x40])  # RTI, used as the NMI/IRQ handler target
    prg[0x7FFA:0x7FFC] = bytes([0x03, 0x80])  # NMI vector -> $8003 (RTI)
    prg[0x7FFC:0x7FFE] = bytes([0x00, 0x80])  # Reset vector -> $8000 (self-loop)
    prg[0x7FFE:0x8000] = bytes([0x03, 0x80])  # IRQ/BRK vector -> $8003 (RTI)

    chr_rom = bytes(CHR_SIZE)  # blank pattern tables

    return bytes(header) + bytes(prg) + chr_rom


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    out = Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_rom())
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
