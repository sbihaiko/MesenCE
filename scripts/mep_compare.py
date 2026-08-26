#!/usr/bin/env python3
"""mep_compare — compara a camada automática (`auto/textures`, xBRZ) com um
HD pack feito por artista, tile a tile (F5, avaliação qualitativa do bootstrap).

Funciona para packs NES cuja chave de tile é intrínseca (CHR RAM: bitmap de
32 hex + paleta). Para cada chave presente nos dois lados monta uma faixa
`original | xBRZ (auto) | artista` e calcula métricas simples:

  * cobertura: quantas chaves do artista o bootstrap também viu (e vice-versa);
  * MAE(xBRZ, artista) vs MAE(nearest, artista): o upscale automático aproxima
    o resultado do artista mais do que o pixel cru?;
  * quantos tiles do artista dependem de <condition> (contexto que a máquina
    ainda não infere — F5.4).

Uso: python3 scripts/mep_compare.py <auto/textures> <pack-do-artista> <saida> [--name Jogo] [--samples 48]
Saída: <saida>/<name>.json, <name>-common.png, <name>-artist-only.png, <name>-auto-only.png
"""
import json
import random
import re
import sys
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
            line = line.strip()
            if line.startswith("<scale>"):
                self.scale = int(line[7:])
            elif line.startswith("<img>"):
                self.images.append(line[5:].strip())
            elif line.startswith("<condition>"):
                self.conditions += 1
            elif "<background>" in line:
                self.backgrounds += 1
            else:
                m = TILE_RE.match(line)
                if not m:
                    continue
                f = m.group("body").split(",")
                if len(f) < 5 or len(f[1]) != 32:
                    continue  # CHR ROM index keys are out of scope here
                self.total_lines += 1
                key = (f[1].upper(), f[2].upper())
                cond = m.group("cond")
                if cond:
                    self.conditioned += 1
                self.tiles.setdefault(key, []).append(dict(img=int(f[0]), x=int(f[3]), y=int(f[4]), cond=cond))
        self.entries = self.tiles
        self._best = {}

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


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    auto, artist, out = Pack(Path(argv[1])), Pack(Path(argv[2])), Path(argv[3])
    name = "game"
    samples = 48
    for i, a in enumerate(argv):
        if a == "--name":
            name = argv[i + 1]
        if a == "--samples":
            samples = int(argv[i + 1])
    out.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(7)

    a_keys, r_keys = set(auto.tiles), set(artist.tiles)
    common = sorted(a_keys & r_keys)
    auto_only = sorted(a_keys - r_keys)
    artist_only = sorted(r_keys - a_keys)
    a_shapes, r_shapes = {k[0] for k in a_keys}, {k[0] for k in r_keys}

    # Tiles the artist left transparent are drawn some other way (usually a
    # conditional <background> of the whole screen): not comparable tile-to-tile
    comparable = [k for k in common if artist.opacity(k) >= 0.1]
    hidden = len(common) - len(comparable)

    # metrics on comparable tiles
    size = 32
    m_xbrz, m_near, closer = [], [], 0
    for key in comparable:
        orig = render_original(*key)
        near = flatten(orig, size)
        xb = flatten(auto.crop(key), size, Image.BILINEAR if auto.scale * 8 > size else Image.NEAREST)
        art = flatten(artist.crop(key), size, Image.BILINEAR if artist.scale * 8 > size else Image.NEAREST)
        a, b = mae(xb, art), mae(near, art)
        m_xbrz.append(a)
        m_near.append(b)
        closer += a < b

    def sample(keys):
        keys = [k for k in keys if is_interesting(k[0])]
        rnd.shuffle(keys)
        return keys[:samples]

    sc = sample(comparable)
    montage([[render_original(*k) for k in sc], [auto.crop(k) for k in sc], [artist.crop(k) for k in sc]], 40,
            ["original", f"auto xBRZ {auto.scale}x", f"artista {artist.scale}x"], out / f"{name}-common.png")
    so = sample(artist_only)
    montage([[render_original(*k) for k in so], [artist.crop(k) for k in so]], 40,
            ["original", "artista"], out / f"{name}-artist-only.png")
    sa = sample(auto_only)
    montage([[render_original(*k) for k in sa], [auto.crop(k) for k in sa]], 40,
            ["original", f"auto xBRZ {auto.scale}x"], out / f"{name}-auto-only.png")

    stats = dict(
        name=name,
        auto=dict(folder=str(auto.folder), scale=auto.scale, tiles=len(a_keys), shapes=len(a_shapes),
                  palettes_per_shape=round(len(a_keys) / max(1, len(a_shapes)), 2)),
        artist=dict(folder=str(artist.folder), scale=artist.scale, tiles=len(r_keys), shapes=len(r_shapes),
                    lines=artist.total_lines, conditioned_lines=artist.conditioned,
                    conditions=artist.conditions, backgrounds=artist.backgrounds,
                    palettes_per_shape=round(len(r_keys) / max(1, len(r_shapes)), 2)),
        common=len(common), auto_only=len(auto_only), artist_only=len(artist_only),
        common_comparable=len(comparable), common_artist_transparent=hidden,
        coverage_of_artist=round(len(common) / max(1, len(r_keys)), 3),
        auto_keys_known_to_artist=round(len(common) / max(1, len(a_keys)), 3),
        mae_xbrz_vs_artist=round(float(np.mean(m_xbrz)), 1) if m_xbrz else None,
        mae_nearest_vs_artist=round(float(np.mean(m_near)), 1) if m_near else None,
        xbrz_closer_than_nearest=round(closer / max(1, len(comparable)), 3),
    )
    (out / f"{name}.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
