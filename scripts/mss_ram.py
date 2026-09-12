#!/usr/bin/env python3
"""Read the NES internal RAM (and a few PPU registers) out of a Mesen save
state, so a headless input chain can be steered by what the game knows.

    scripts/mss_ram.py <file.mss>                 # 2 KB hex dump
    scripts/mss_ram.py <file.mss> 0x32 0x64 0x30  # named bytes, one line
    scripts/mss_ram.py <file.mss> --diff <other.mss>  # bytes that differ

Layout (Mesen 2, NES): "MSS" header, video data zlib at 0x23, then uint32
ROM name length + name, then the Serializer blob (1 byte compressed flag,
uint32 original size, uint32 stored size, zlib data). Blob entries are
`key\\0` + uint32 size + bytes; the RAM is `memoryManager.internalRam`.
"""
import struct, sys, zlib


def blob(path):
    d = open(path, "rb").read()
    z = zlib.decompressobj()
    z.decompress(d[0x23:])
    rest = z.unused_data
    n = struct.unpack("<I", rest[:4])[0]
    p = 4 + n
    comp = rest[p]
    orig, size = struct.unpack("<II", rest[p + 1:p + 9])
    return zlib.decompress(rest[p + 9:p + 9 + size]) if comp else rest[p + 1:p + 1 + orig]


def val(b, key):
    k = key.encode() + b"\0"
    i = b.index(k) + len(k)
    sz = struct.unpack("<I", b[i:i + 4])[0]
    return b[i + 4:i + 4 + sz]


def ram(path):
    return val(blob(path), "memoryManager.internalRam")


def fine_scroll(path):
    b = blob(path)
    tmp = int.from_bytes(val(b, "ppu.tmpVideoRamAddr"), "little")
    xs = int.from_bytes(val(b, "ppu.xScroll"), "little")
    return ((tmp & 0x1f) << 3) | xs


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    r = ram(argv[1])
    if len(argv) > 3 and argv[2] == "--diff":
        o = ram(argv[3])
        for i in range(len(r)):
            if r[i] != o[i]:
                print(f"${i:04X} {r[i]:3d} {o[i]:3d}")
        return 0
    if len(argv) > 2:
        print(" ".join(f"${int(a, 0):04X}={r[int(a, 0)]}" for a in argv[2:]), f"scroll={fine_scroll(argv[1])}")
        return 0
    for i in range(0, len(r), 32):
        print(f"${i:04X}: " + " ".join(f"{x:02X}" for x in r[i:i + 32]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
