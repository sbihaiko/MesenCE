#!/usr/bin/env python3
"""Gera zips sintéticos para exercitar o fallback estrutural do ADR-0120
(scripts/mep_lint.py's find_fallback_subfolder / scripts/checks/
verify_mep_fallback_lint_fixture.sh).

Nenhum dos dois zips tem pack.json na raiz nem nome de arquivo igual ao da
ROM — as duas convenções existentes (ADR-0040/ADR-0049) já falham por
construção, então só o fallback (ou a rejeição ambígua dele) decide o
resultado:

  accept     <out>/mep-fallback-accept.zip   um único wrapper (formato de
             release zip real, "Contra80s-v1.1/Contra (U) [!]/") contendo a
             convenção completa (textures/hires.txt, synth/preset.cfg) mais
             um arquivo de promo solto ao lado ("Contra80s-v1.1/README.txt")
             que não deve confundir a busca — candidato único, deve ser
             aceito.
  reject     <out>/mep-fallback-reject.zip   dois subdiretórios distintos
             ("PackA/", "PackB/"), cada um com sua própria convenção
             completa — dois candidatos estruturalmente válidos, ambíguo,
             deve ser rejeitado (nenhuma seção encontrada).
  malformed  <out>/mep-fallback-malformed-manifest.zip   mesmo wrapper único
             do "accept", mas com um pack.json inválido (JSON quebrado)
             dentro do subdiretório descoberto — pack.json é um dos
             FALLBACK_SUFFIXES (marcador de aceite), então isto prova que o
             fallback linta o manifest descoberto por inteiro em vez de só
             usá-lo como sinal estrutural (ver o fix de segurança no
             histórico de mep_lint.py, revision cycle do T3): deve ser
             rejeitado.

Uso:
  python3 scripts/gen_mep_fallback_test_pack.py <out-dir> [kinds...]
  (sem kinds: gera accept e reject)
"""
import sys
import zipfile
from pathlib import Path

HIRES_TXT = "<ver>106\n<scale>1\n"
PRESET_CFG = "[Studio]\nCompThreshold=0.5\n"

# Formato típico de um zip de release do GitHub: "<Repo>-<tag>/<Jogo>/..."
ACCEPT_WRAPPER = "Contra80s-v1.1/Contra (U) [!]"


def _write_zip(path: Path, entries):
    if path.exists():
        path.unlink()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, text in entries:
            z.writestr(rel, text)


def write_accept_zip(path: Path):
    """Um único candidato estrutural: aceito pelo fallback (depth 4, no
    limite de FALLBACK_MAX_DEPTH/kMepFallbackMaxDepth/FallbackMaxDepth)."""
    _write_zip(path, [
        (f"{ACCEPT_WRAPPER}/textures/hires.txt", HIRES_TXT),
        (f"{ACCEPT_WRAPPER}/synth/preset.cfg", PRESET_CFG),
        ("Contra80s-v1.1/README.txt", "release wrapper promo text, not a pack layer\n"),
    ])


def write_reject_zip(path: Path):
    """Dois candidatos estruturalmente válidos e distintos: ambíguo, o
    fallback deve recusar (retornar 'nada encontrado') em vez de adivinhar."""
    _write_zip(path, [
        ("PackA/textures/hires.txt", HIRES_TXT),
        ("PackA/synth/preset.cfg", PRESET_CFG),
        ("PackB/textures/hires.txt", HIRES_TXT),
        ("PackB/synth/preset.cfg", PRESET_CFG),
    ])


def write_malformed_manifest_zip(path: Path):
    """Mesmo wrapper único do accept, mas com um pack.json inválido dentro
    do subdiretório descoberto: prova que o fallback linta o manifest
    descoberto (não só usa sua presença como sinal estrutural)."""
    _write_zip(path, [
        (f"{ACCEPT_WRAPPER}/pack.json", "{ isto não é json"),
        (f"{ACCEPT_WRAPPER}/textures/hires.txt", HIRES_TXT),
    ])


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    out = Path(sys.argv[1])
    kinds = sys.argv[2:] or ["accept", "reject"]
    out.mkdir(parents=True, exist_ok=True)

    for kind in kinds:
        if kind == "accept":
            write_accept_zip(out / "mep-fallback-accept.zip")
        elif kind == "reject":
            write_reject_zip(out / "mep-fallback-reject.zip")
        elif kind == "malformed":
            write_malformed_manifest_zip(out / "mep-fallback-malformed-manifest.zip")
        else:
            print(f"kind desconhecido: {kind}")
            return 1
        print(f"gerado: {kind}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
