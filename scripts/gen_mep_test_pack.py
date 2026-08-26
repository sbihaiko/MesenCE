#!/usr/bin/env python3
"""Gera packs MEP v1 de teste para uma ROM (F3.1 — validação headless).

Calcula o SHA-1 No-Intro da ROM (ADR-0039: .nes sem header iNES/trainer,
SNES sem copier header, demais formatos arquivo inteiro) e escreve, na pasta
EnhancementPacks/ indicada, os contêineres pedidos:

  dir       <out>/<name>/pack.json            (pack em diretório)
  zip       <out>/<name>.zip                  (pack em zip, pack.json na raiz)
  badhash   pack válido que NÃO casa (sha1 de zeros)
  badjson   pack.json malformado (deve ser rejeitado com log)
  slip      zip com entrada '../evil.txt' (deve ser rejeitado — zip-slip)
  major     pack com "mep": "2.0.0" (major desconhecido — rejeitado)

Uso:
  python3 scripts/gen_mep_test_pack.py <rom> <EnhancementPacks-dir> [kinds...] [--textures=<pasta>]
  (sem kinds: gera dir e zip; --textures copia uma pasta de HD pack real —
  ex. a saída de `headless_record ... hdpack` — para textures/ em vez do
  hires.txt vazio, permitindo o screenshot 1:1 da F3.2)

Imprime o SHA-1 No-Intro calculado na saída padrão (para comparar com o
"[MEP] ... matches ROM sha1 ..." do log do core).
"""
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ZERO_SHA1 = "0" * 40


def no_intro_sha1(rom: Path) -> str:
    data = rom.read_bytes()
    ext = rom.suffix.lower()
    offset = 0
    if ext == ".nes" and data[:4] == b"NES\x1a":
        offset = 16 + (512 if data[6] & 0x04 else 0)
    elif ext in {".sfc", ".smc", ".swc", ".fig", ".bs", ".st"} and len(data) % 1024 == 512:
        offset = 512
    return hashlib.sha1(data[offset:]).hexdigest().upper()


def system_for(rom: Path) -> str:
    return {
        ".nes": "nes", ".gb": "gb", ".gbc": "gbc", ".sms": "sms", ".gg": "gg",
        ".sg": "sg1000", ".sfc": "snes", ".smc": "snes",
    }.get(rom.suffix.lower(), "nes")


def pack_json(name: str, system: str, sha1: str, mep="1.0.0") -> dict:
    return {
        "mep": mep,
        "name": name,
        "version": "1.0.0",
        "author": "gen_mep_test_pack.py",
        "license": "CC0-1.0",
        "targets": [{"system": system, "sha1": sha1, "name": "test rom"}],
        "sections": {
            "textures": {"path": "textures/"},
            "synth": {"path": "synth/preset.cfg"},
            "future-section": {"path": "ignored/"},
        },
    }


CONTENT = {
    "textures/hires.txt": "<ver>106\n<scale>1\n",
    "synth/preset.cfg": "[Studio]\nCompThreshold=0.5\n",
}


TEXTURES_SRC = None  # pasta de HD pack real a copiar para textures/


def write_dir(root: Path, meta: dict, content=CONTENT):
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / "pack.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    for rel, text in content.items():
        if TEXTURES_SRC and rel.startswith("textures/"):
            continue
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    if TEXTURES_SRC:
        shutil.copytree(TEXTURES_SRC, root / "textures")


def write_zip(path: Path, meta, content=CONTENT, extra_entries=()):
    if path.exists():
        path.unlink()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.json", meta if isinstance(meta, str) else json.dumps(meta, indent=2))
        for rel, text in content.items():
            if TEXTURES_SRC and rel.startswith("textures/"):
                continue
            z.writestr(rel, text)
        if TEXTURES_SRC:
            for f in sorted(Path(TEXTURES_SRC).rglob("*")):
                if f.is_file():
                    z.write(f, "textures/" + f.relative_to(TEXTURES_SRC).as_posix())
        for rel, text in extra_entries:
            z.writestr(rel, text)


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    global TEXTURES_SRC
    args = [a for a in sys.argv[1:] if not a.startswith("--textures=")]
    for a in sys.argv[1:]:
        if a.startswith("--textures="):
            TEXTURES_SRC = Path(a.split("=", 1)[1])
    rom = Path(args[0])
    out = Path(args[1])
    kinds = args[2:] or ["dir", "zip"]
    out.mkdir(parents=True, exist_ok=True)

    sha1 = no_intro_sha1(rom)
    system = system_for(rom)
    print(f"no-intro sha1: {sha1} (system {system})")

    for kind in kinds:
        if kind == "dir":
            write_dir(out / "mep-test-dir", pack_json("MEP test (dir)", system, sha1))
        elif kind == "zip":
            write_zip(out / "mep-test-zip.zip", pack_json("MEP test (zip)", system, sha1))
        elif kind == "badhash":
            write_dir(out / "mep-test-badhash", pack_json("MEP no match", system, ZERO_SHA1))
        elif kind == "badjson":
            root = out / "mep-test-badjson"
            write_dir(root, pack_json("x", system, sha1))
            (root / "pack.json").write_text('{"mep": "1.0.0", "name": trailing', encoding="utf-8")
        elif kind == "slip":
            write_zip(out / "mep-test-slip.zip", pack_json("MEP slip", system, sha1),
                      extra_entries=[("../evil.txt", "pwned")])
        elif kind == "major":
            write_dir(out / "mep-test-major", pack_json("MEP v2", system, sha1, mep="2.0.0"))
        else:
            print(f"kind desconhecido: {kind}")
            return 1
        print(f"gerado: {kind}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
