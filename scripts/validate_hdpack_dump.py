#!/usr/bin/env python3
"""Valida um pack gerado pelo HD Pack Builder de GB/SMS (F2.2): re-renderiza
cada linha <tile> do hires.txt a partir dos dados + chave de paleta (semântica
de ADR-0036/ADR-0037 e docs/specs/hires-gbsms-v1-draft.md §3.2) e compara
pixel a pixel com a folha PNG dumpeada. É a prova do critério de sucesso do
PRD F2: um replacement 1:1 neutro reconstruído só do pack é idêntico ao que o
emulador renderizou.

Uso: python3 scripts/validate_hdpack_dump.py <dir-do-pack> [--dmg-shades RRGGBB,RRGGBB,RRGGBB,RRGGBB]
Sai com código != 0 na primeira divergência.
"""
import argparse
import sys
from pathlib import Path

from PIL import Image

FILLER = (255, 0, 255, 255)  # magenta de célula vazia (0xFFFF00FF ARGB)


def expand5(v):
    return ((v << 3) | (v >> 2)) & 0xFF


def rgb555_to_rgba(c):
    # Mesma convenção de ColorUtilities::Rgb555ToArgb: b nos bits 10-14,
    # g nos bits 5-9, r nos bits 0-4
    b = expand5((c >> 10) & 0x1F)
    g = expand5((c >> 5) & 0x1F)
    r = expand5(c & 0x1F)
    return (r, g, b, 255)


def rgb222_to_555(v):
    # Réplica exata de ColorUtilities::Rgb222To555
    return (
        ((v & 0x30) << 9) | ((v & 0x30) << 7) | ((v & 0x20) << 5) |
        ((v & 0x0C) << 6) | ((v & 0x0C) << 4) | ((v & 0x08) << 2) |
        ((v & 0x03) << 3) | ((v & 0x03) << 1) | ((v & 0x02) >> 1)
    ) & 0x7FFF


def rgb444_to_555(v):
    # Réplica exata de ColorUtilities::Rgb444To555
    return (
        ((v & 0xF00) << 3) | ((v & 0x800) >> 1) |
        ((v & 0x0F0) << 2) | ((v & 0x080) >> 2) |
        ((v & 0x00F) << 1) | ((v & 0x008) >> 3)
    ) & 0x7FFF


TRANSPARENT = (255, 255, 255, 0)  # 0x00FFFFFF


def render_gb_tile(data, palkey, dmg_shades):
    is_obj = palkey[0] == 0x01
    if len(palkey) == 2:  # DMG: TT + valor de BGP/OBPx
        pal_byte = palkey[1]
        colors = [dmg_shades[(pal_byte >> (i * 2)) & 0x03] for i in range(4)]
    elif len(palkey) == 9:  # CGB: TT + 4x RGB555 big-endian
        colors = [rgb555_to_rgba((palkey[1 + i * 2] << 8) | palkey[2 + i * 2]) for i in range(4)]
    else:
        raise ValueError(f"chave de paleta GB com tamanho inválido: {len(palkey)}")

    pixels = []
    for y in range(8):
        low, high = data[y * 2], data[y * 2 + 1]
        for x in range(8):
            color = ((low >> (7 - x)) & 1) | (((high >> (7 - x)) & 1) << 1)
            pixels.append(TRANSPARENT if is_obj and color == 0 else colors[color])
    return pixels


def render_sms_tile(data, palkey, is_gg):
    is_obj = palkey[0] == 0x01
    snapshot = palkey[2:]
    if is_gg:
        assert len(snapshot) == 32, f"snapshot CRAM GG deve ter 32 bytes, tem {len(snapshot)}"
        colors = [rgb555_to_rgba(rgb444_to_555((snapshot[i * 2] << 8) | snapshot[i * 2 + 1])) for i in range(16)]
    else:
        assert len(snapshot) == 16, f"snapshot CRAM SMS deve ter 16 bytes, tem {len(snapshot)}"
        colors = [rgb555_to_rgba(rgb222_to_555(v)) for v in snapshot]

    pixels = []
    for y in range(8):
        row = data[y * 4:y * 4 + 4]
        for x in range(8):
            color = (
                ((row[0] >> (7 - x)) & 1) |
                (((row[1] >> (7 - x)) & 1) << 1) |
                (((row[2] >> (7 - x)) & 1) << 2) |
                (((row[3] >> (7 - x)) & 1) << 3)
            )
            pixels.append(TRANSPARENT if is_obj and color == 0 else colors[color])
    return pixels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pack_dir", type=Path)
    ap.add_argument("--dmg-shades", default="FFFFFF,B0B0B0,686868,000000",
                    help="4 cores RGB888 dos tons DMG usados na gravação (default do core)")
    args = ap.parse_args()

    hires = args.pack_dir / "hires.txt"
    if not hires.exists():
        sys.exit(f"ERRO: {hires} não existe")

    # O core converte a cor de config RGB888 -> RGB555 -> RGB888 expandido
    dmg_shades = []
    for tok in args.dmg_shades.split(","):
        v = int(tok, 16)
        c555 = (((v & 0xF8) << 7) | ((v & 0xF800) >> 6) | ((v & 0xF80000) >> 19)) & 0x7FFF
        dmg_shades.append(rgb555_to_rgba(c555))

    lines = [l.strip() for l in hires.read_text().splitlines() if l.strip() and not l.startswith("#")]
    tags = dict()
    imgs = []
    tiles = []
    for l in lines:
        if l.startswith("<img>"):
            imgs.append(l[5:])
        elif l.startswith("<tile>"):
            tiles.append(l[6:].split(","))
        elif l.startswith("<"):
            tags[l[1:l.index(">")]] = l[l.index(">") + 1:]

    system = tags.get("system")
    scale = int(tags.get("scale", "1"))
    assert int(tags["ver"]) >= 200, "pack GB/SMS deve ter <ver> >= 200"
    assert system in ("gb", "gbc", "sms", "gg"), f"<system> inesperado: {system}"

    sheets = [Image.open(args.pack_dir / name).convert("RGBA") for name in imgs]

    seen_keys = set()
    errors = 0
    for fields in tiles:
        png_idx, data_hex, pal_hex, x, y = int(fields[0]), fields[1], fields[2], int(fields[3]), int(fields[4])
        data = bytes.fromhex(data_hex)
        palkey = bytes.fromhex(pal_hex)

        key = (data_hex, pal_hex)
        if key in seen_keys:
            print(f"ERRO: chave duplicada no hires.txt: {data_hex[:16]}.../{pal_hex}")
            errors += 1
            continue
        seen_keys.add(key)

        if system in ("gb", "gbc"):
            assert len(data) == 16, "tile GB deve ter 16 bytes"
            expected = render_gb_tile(data, palkey, dmg_shades)
        else:
            assert len(data) == 32, "tile SMS/GG deve ter 32 bytes"
            expected = render_sms_tile(data, palkey, system == "gg")

        sheet = sheets[png_idx]
        for py in range(8):
            for px in range(8):
                exp = expected[py * 8 + px]
                # Prescale: todo bloco scale x scale deve ser uniforme
                for sy in range(scale):
                    for sx in range(scale):
                        got = sheet.getpixel((x + px * scale + sx, y + py * scale + sy))
                        if exp[3] == 0:
                            ok = got[3] == 0
                        else:
                            ok = got == exp
                        if not ok:
                            print(f"ERRO: tile @png{png_idx} ({x},{y}) pixel ({px},{py}): esperado {exp}, PNG tem {got}")
                            errors += 1
                            if errors > 20:
                                sys.exit("abortando: erros demais")
    if errors:
        sys.exit(f"{errors} divergências — pack NÃO é replacement 1:1")
    print(f"OK: {len(tiles)} tiles em {len(sheets)} folha(s) PNG re-renderizam 1:1 ({system}, scale {scale})")


if __name__ == "__main__":
    main()
