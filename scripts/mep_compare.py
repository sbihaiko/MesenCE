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
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from mep_compare_pack import Pack, flatten, is_interesting, mae, montage, render_original


def parse_args(argv):
    name, samples = "game", 48
    for i, a in enumerate(argv):
        if a == "--name":
            name = argv[i + 1]
        if a == "--samples":
            samples = int(argv[i + 1])
    return Path(argv[1]), Path(argv[2]), Path(argv[3]), name, samples


def compute_key_sets(auto: Pack, artist: Pack):
    a_keys, r_keys = set(auto.tiles), set(artist.tiles)
    common = sorted(a_keys & r_keys)
    auto_only = sorted(a_keys - r_keys)
    artist_only = sorted(r_keys - a_keys)
    a_shapes, r_shapes = {k[0] for k in a_keys}, {k[0] for k in r_keys}
    return a_keys, r_keys, common, auto_only, artist_only, a_shapes, r_shapes


def compute_comparable_metrics(auto: Pack, artist: Pack, common, size=32):
    # Tiles the artist left transparent are drawn some other way (usually a
    # conditional <background> of the whole screen): not comparable tile-to-tile
    comparable = [k for k in common if artist.opacity(k) >= 0.1]
    hidden = len(common) - len(comparable)

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
    return comparable, hidden, m_xbrz, m_near, closer


def sample_keys(keys, samples, rnd):
    keys = [k for k in keys if is_interesting(k[0])]
    rnd.shuffle(keys)
    return keys[:samples]


def write_montages(auto: Pack, artist: Pack, comparable, artist_only, auto_only, out: Path, name, samples, rnd):
    sc = sample_keys(comparable, samples, rnd)
    montage([[render_original(*k) for k in sc], [auto.crop(k) for k in sc], [artist.crop(k) for k in sc]], 40,
            ["original", f"auto xBRZ {auto.scale}x", f"artista {artist.scale}x"], out / f"{name}-common.png")
    so = sample_keys(artist_only, samples, rnd)
    montage([[render_original(*k) for k in so], [artist.crop(k) for k in so]], 40,
            ["original", "artista"], out / f"{name}-artist-only.png")
    sa = sample_keys(auto_only, samples, rnd)
    montage([[render_original(*k) for k in sa], [auto.crop(k) for k in sa]], 40,
            ["original", f"auto xBRZ {auto.scale}x"], out / f"{name}-auto-only.png")


def build_stats(name, auto: Pack, artist: Pack, key_sets, comparable_metrics):
    a_keys, r_keys, common, auto_only, artist_only, a_shapes, r_shapes = key_sets
    comparable, hidden, m_xbrz, m_near, closer = comparable_metrics
    return dict(
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


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    auto_path, artist_path, out, name, samples = parse_args(argv)
    auto, artist = Pack(auto_path), Pack(artist_path)
    out.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(7)

    key_sets = compute_key_sets(auto, artist)
    comparable_metrics = compute_comparable_metrics(auto, artist, key_sets[2])
    comparable, artist_only, auto_only = comparable_metrics[0], key_sets[4], key_sets[3]
    write_montages(auto, artist, comparable, artist_only, auto_only, out, name, samples, rnd)

    stats = build_stats(name, auto, artist, key_sets, comparable_metrics)
    (out / f"{name}.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
