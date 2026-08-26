"""mep_compare_pack — HD pack parsing and per-tile rendering/scoring helpers
used by `mep_compare.py`. Split out of that CLI module so each file stays
under the repo's file/function size limits (`scripts/AGENTS.md`); no
behavior change versus the code this was extracted from.
"""
import re
from pathlib import Path

import numpy as np
from PIL import Image

# 2C02 (mesma tabela de Core/NES/NesDefaultVideoFilter.cpp)
_PAL = [0x666666, 0x002A88, 0x1412A7, 0x3B00A4, 0x5C007E, 0x6E0040, 0x6C0600, 0x561D00, 0x333500, 0x0B4800, 0x005200, 0x004F08, 0x00404D, 0x000000, 0x000000, 0x000000,
        0xADADAD, 0x155FD9, 0x4240FF, 0x7527FE, 0xA01ACC, 0xB71E7B, 0xB53120, 0x994E00, 0x6B6D00, 0x388700, 0x0C9300, 0x008F32, 0x007C8D, 0x000000, 0x000000, 0x000000,
        0xFFFEFF, 0x64B0FF, 0x9290FF, 0xC676FF, 0xF36AFF, 0xFE6ECC, 0xFE8170, 0xEA9E22, 0xBCBE00, 0x88D800, 0x5CE430, 0x45E082, 0x48CDDE, 0x4F4F4F, 0x000000, 0x000000,
        0xFFFEFF, 0xC0DFFF, 0xD3D2FF, 0xE8C8FF, 0xFBC2FF, 0xFEC4EA, 0xFECCC5, 0xF7D8A5, 0xE4E594, 0xCFEF96, 0xBDF4AB, 0xB3F3CC, 0xB5EBF2, 0xB8B8B8, 0x000000, 0x000000]
NES_PALETTE = [((c >> 16) & 255, (c >> 8) & 255, c & 255) for c in _PAL]

TILE_RE = re.compile(r"^(\[(?P<cond>[^\]]*)\])?<tile>(?P<body>.*)$")


class Pack:
    def __init__(self, folder: Path):
        self.folder = folder
        self.scale = 1
        self.images = []
        self.tiles = {}  # (chr, palette) -> dict(img, x, y, cond)
        self.conditioned = 0
        self.total_lines = 0
        self.backgrounds = 0
        self.conditions = 0
        self._cache = {}
        self._parse()

    def _parse(self):
        text = (self.folder / "hires.txt").read_text(errors="replace")
        for line in text.splitlines():
            self._parse_line(line.strip())
        self.entries = self.tiles
        self._best = {}

    def _parse_line(self, line):
        if line.startswith("<scale>"):
            self.scale = int(line[7:])
        elif line.startswith("<img>"):
            self.images.append(line[5:].strip())
        elif line.startswith("<condition>"):
            self.conditions += 1
        elif "<background>" in line:
            self.backgrounds += 1
        else:
            self._parse_tile_line(line)

    def _parse_tile_line(self, line):
        m = TILE_RE.match(line)
        if not m:
            return
        f = m.group("body").split(",")
        if len(f) < 5 or len(f[1]) != 32:
            return  # CHR ROM index keys are out of scope here
        self.total_lines += 1
        key = (f[1].upper(), f[2].upper())
        cond = m.group("cond")
        if cond:
            self.conditioned += 1
        self.tiles.setdefault(key, []).append(dict(img=int(f[0]), x=int(f[3]), y=int(f[4]), cond=cond))

    def image(self, idx):
        if idx not in self._cache:
            p = self.folder / self.images[idx]
            if not p.exists():  # case-insensitive fallback
                cands = [q for q in self.folder.iterdir() if q.name.lower() == self.images[idx].lower()]
                p = cands[0] if cands else p
            self._cache[idx] = Image.open(p).convert("RGBA")
        return self._cache[idx]

    def crop(self, key):
        # Several entries can share a key (conditional overlays, often transparent
        # "priority" layers): use the most opaque one, unconditioned first on ties
        if key not in self._best:
            s = self.scale * 8
            best, best_score = None, -1.0
            for t in sorted(self.tiles[key], key=lambda t: t["cond"] is not None):
                c = self.image(t["img"]).crop((t["x"], t["y"], t["x"] + s, t["y"] + s))
                score = float(np.asarray(c)[..., 3].mean())
                if score > best_score:
                    best, best_score = c, score
                if score >= 254:
                    break
            self._best[key] = (best, best_score)
        return self._best[key][0]

    def opacity(self, key):
        self.crop(key)
        return self._best[key][1] / 255.0


def render_original(chr_hex: str, pal_hex: str) -> Image.Image:
    data = bytes.fromhex(chr_hex)
    pal = [NES_PALETTE[int(pal_hex[i:i + 2], 16) & 0x3F] for i in range(0, 8, 2)]
    img = Image.new("RGBA", (8, 8))
    px = img.load()
    for y in range(8):
        lo, hi = data[y], data[y + 8]
        for x in range(8):
            bit = 7 - x
            c = ((lo >> bit) & 1) | (((hi >> bit) & 1) << 1)
            px[x, y] = pal[c] + (255,)
    return img


def flatten(img: Image.Image, size: int, resample=Image.NEAREST) -> np.ndarray:
    bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
    bg.alpha_composite(img)
    return np.asarray(bg.convert("RGB").resize((size, size), resample), dtype=np.float32)


def mae(a, b):
    return float(np.abs(a - b).mean())


def montage(rows, cell, labels, path: Path):
    """rows: list of lists of PIL images (same count per row)."""
    if not rows or not rows[0]:
        return
    n = len(rows[0])
    pad = 2
    label_w = 70
    w = label_w + n * (cell + pad)
    h = len(rows) * (cell + pad)
    out = Image.new("RGB", (w, h), (24, 24, 28))
    from PIL import ImageDraw
    d = ImageDraw.Draw(out)
    for r, (imgs, label) in enumerate(zip(rows, labels)):
        d.text((4, r * (cell + pad) + cell // 2 - 5), label, fill=(200, 200, 200))
        for c, im in enumerate(imgs):
            bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
            bg.alpha_composite(im.convert("RGBA"))
            out.paste(bg.convert("RGB").resize((cell, cell), Image.NEAREST), (label_w + c * (cell + pad), r * (cell + pad)))
    out.save(path)


def is_interesting(chr_hex):
    data = bytes.fromhex(chr_hex)
    return len(set(data)) > 2  # skip blank / solid / trivially flat tiles
