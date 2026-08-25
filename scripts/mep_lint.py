#!/usr/bin/env python3
"""mep_lint — validação offline de packs (F5.1, docs/roadmap/plano-execucao-F5.md).

Aceita um diretório ou um .zip e verifica, sem rodar o emulador:

  * pack.json (opcional na convenção de pasta — ADR-0049): campos MUST da spec
    MEP-v1, semver, hashes, paths seguros, patches[] (ADR-0044);
  * layout da convenção: textures/hires.txt, audio/hires.txt, synth/preset.cfg
    e as mesmas camadas em auto/;
  * hires.txt NES (HDNes): tags conhecidas, arquivos referenciados existentes
    (<img>, <background>, <bgm>, <sfx>, <patch>), <condition> com tipo válido,
    coordenadas de *AtPosition dentro de 256×240, offsets de *Nearby dentro do
    range da tela (o off-by-one que derrubava o emulador é reportado aqui),
    conditions permitidas por tag (tileNearby/spriteNearby não valem em
    <background>), chaves <tile> duplicadas, PNG com dimensão múltipla do scale;
  * hires.txt GB/SMS (<ver>200): <system>, <img> existentes, <tile> com 7 campos,
    blobs hex, chaves duplicadas.

Saída: uma linha por achado (`error|warning|info  arquivo:linha  mensagem`) e um
resumo; exit code 1 quando há erro, 0 caso contrário.

Uso: python3 scripts/mep_lint.py <pasta-ou-zip> [--quiet]
"""
import json
import re
import struct
import sys
import zipfile
from pathlib import Path, PurePosixPath

SECTION_PATHS = {"textures": "textures", "audio": "audio", "synth": "synth/preset.cfg"}
PROBES = {"textures": "textures/hires.txt", "audio": "audio/hires.txt", "synth": "synth/preset.cfg"}
AUDIO_ALT_PROBE = "audio/fingerprints.json"
KNOWN_SYSTEMS = {"nes", "gb", "gbc", "sms", "gg", "sg1000", "coleco", "snes"}
NES_TAGS = {"ver", "scale", "supportedRom", "img", "tile", "background", "condition", "bgm", "sfx", "patch", "overscan", "options", "addition", "fallback"}
GBSMS_TAGS = {"ver", "scale", "system", "img", "tile", "supportedRom"}
COND_TYPES = {"tileAtPosition", "tileNearby", "spriteAtPosition", "spriteNearby", "memoryCheck", "ppuMemoryCheck", "memoryCheckConstant", "ppuMemoryCheckConstant", "frameRange", "positionCheckX", "positionCheckY", "originPositionCheckX", "originPositionCheckY"}
GLOBAL_CONDS = {"hmirror", "vmirror", "bgpriority", "sppalette0", "sppalette1", "sppalette2", "sppalette3"}
BG_FORBIDDEN = {"tileNearby", "spriteNearby", "spriteAtPosition"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
HEX40 = re.compile(r"^[0-9A-Fa-f]{40}$")


class Source:
    """Uniformiza pasta e zip: listagem, leitura de bytes e texto."""

    def __init__(self, path: Path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if path.is_file() else None
        if self.zip:
            self.names = {n.replace("\\", "/") for n in self.zip.namelist()}
        else:
            self.names = {p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()}

    def exists(self, rel: str) -> bool:
        return rel in self.names

    def exists_icase(self, rel: str):
        """Nome real quando o arquivo existe só com outra capitalização (macOS/
        Windows carregam, Linux não), senão None."""
        if not hasattr(self, "_lower"):
            self._lower = {n.lower(): n for n in self.names}
        return self._lower.get(rel.lower())

    def read(self, rel: str) -> bytes:
        if self.zip:
            return self.zip.read(rel)
        return (self.path / rel).read_bytes()

    def text(self, rel: str) -> str:
        return self.read(rel).decode("utf-8", errors="replace")


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, where, msg):
        self.items.append((level, where, msg))

    def error(self, where, msg):
        self.add("error", where, msg)

    def warning(self, where, msg):
        self.add("warning", where, msg)

    def info(self, where, msg):
        self.add("info", where, msg)

    @property
    def errors(self):
        return sum(1 for i in self.items if i[0] == "error")

    @property
    def warnings(self):
        return sum(1 for i in self.items if i[0] == "warning")


def safe_rel(path: str):
    p = path.replace("\\", "/")
    if p.startswith("/") or ":" in p:
        return None
    parts = [x for x in p.split("/") if x not in ("", ".")]
    if ".." in parts:
        return None
    return "/".join(parts)


def png_size(data: bytes):
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def lint_pack_json(src: Source, rep: Report):
    where = "pack.json"
    try:
        root = json.loads(src.text("pack.json"))
    except Exception as exc:  # noqa: BLE001
        rep.error(where, f"JSON inválido: {exc}")
        return {}
    if not isinstance(root, dict):
        rep.error(where, "raiz deve ser um objeto")
        return {}
    for key in ("mep", "name", "version", "license"):
        if not isinstance(root.get(key), str) or not root[key]:
            rep.error(where, f"campo obrigatório ausente/inválido: '{key}'")
    if isinstance(root.get("mep"), str):
        if not SEMVER.match(root["mep"]):
            rep.error(where, f"'mep' não é semver: {root['mep']}")
        elif not root["mep"].startswith("1."):
            rep.error(where, f"major MEP não suportado: {root['mep']}")
    if isinstance(root.get("version"), str) and not SEMVER.match(root["version"]):
        rep.error(where, f"'version' não é semver: {root['version']}")
    targets = root.get("targets")
    if not isinstance(targets, list) or not targets:
        rep.error(where, "'targets' deve ser array não vazio")
    else:
        for i, t in enumerate(targets):
            if not isinstance(t, dict):
                rep.error(where, f"targets[{i}] deve ser objeto")
                continue
            if t.get("system") not in KNOWN_SYSTEMS:
                rep.error(where, f"targets[{i}].system desconhecido: {t.get('system')}")
            if not isinstance(t.get("sha1"), str) or not HEX40.match(t["sha1"]):
                rep.error(where, f"targets[{i}].sha1 deve ter 40 hex")
    patches = root.get("patches")
    if patches is not None:
        if not isinstance(patches, list):
            rep.error(where, "'patches' deve ser array")
        else:
            for i, p in enumerate(patches):
                if not isinstance(p, dict) or not isinstance(p.get("sha1"), str) or not isinstance(p.get("file"), str):
                    rep.error(where, f"patches[{i}] precisa de 'sha1' e 'file'")
                    continue
                if not HEX40.match(p["sha1"]):
                    rep.error(where, f"patches[{i}].sha1 deve ter 40 hex")
                rel = safe_rel(p["file"])
                if rel is None:
                    rep.error(where, f"patches[{i}].file inseguro: {p['file']}")
                elif not src.exists(rel):
                    rep.error(where, f"patches[{i}].file não existe: {rel}")
    sections = root.get("sections")
    found = {}
    if not isinstance(sections, dict):
        rep.error(where, "'sections' deve ser objeto")
    else:
        for name, sec in sections.items():
            if name not in SECTION_PATHS:
                rep.info(where, f"seção desconhecida ignorada: {name}")
                continue
            if not isinstance(sec, dict) or not isinstance(sec.get("path"), str):
                rep.error(where, f"seção '{name}' precisa de 'path'")
                continue
            rel = safe_rel(sec["path"])
            if rel is None:
                rep.error(where, f"seção '{name}': path inseguro '{sec['path']}'")
                continue
            probe = rel if name == "synth" else (f"{rel}/hires.txt" if rel else "hires.txt")
            if not src.exists(probe):
                rep.error(where, f"seção '{name}': '{probe}' não existe")
            found[name] = rel
        if not found:
            rep.error(where, "'sections' precisa de textures/audio/synth")
    return found


def parse_line(line: str):
    """Devolve (conds, tag, params) de uma linha `[c1&c2]<tag>params`."""
    conds = []
    if line.startswith("["):
        end = line.find("]")
        if end < 0:
            return None
        conds = [c for c in line[1:end].split("&") if c]
        line = line[end + 1:]
    if not line.startswith("<"):
        return None
    end = line.find(">")
    if end < 0:
        return None
    return conds, line[1:end], line[end + 1:]


def lint_nes_hires(src: Source, rel: str, rep: Report):
    folder = str(PurePosixPath(rel).parent)
    folder = "" if folder == "." else folder + "/"
    text = src.text(rel)
    version = 0
    scale = 1
    imgs = {}
    conds = {}
    tile_keys = {}
    cond_kinds = {}
    dups = []
    missing = {}
    badcase = {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r").strip()
        where = f"{rel}:{n}"
        if not line or line.startswith("#"):
            continue
        parsed = parse_line(line)
        if not parsed:
            rep.warning(where, f"linha não reconhecida: {line[:60]}")
            continue
        used, tag, params = parsed
        tokens = params.split(",") if params else []
        if tag not in NES_TAGS:
            rep.warning(where, f"tag desconhecida <{tag}>")
            continue
        for c in used:
            base = c[1:] if c.startswith("!") else c
            if base not in conds and base not in GLOBAL_CONDS:
                rep.error(where, f"condition '{base}' usada antes de ser definida (ou inexistente)")
            elif tag == "background" and cond_kinds.get(base) in BG_FORBIDDEN:
                rep.error(where, f"condition '{base}' ({cond_kinds[base]}) não é válida em <background>")
        if tag == "ver":
            version = int(tokens[0]) if tokens and tokens[0].isdigit() else 0
            if version < 100:
                rep.warning(where, f"<ver>{version} é formato legado (pré-100)")
        elif tag == "scale":
            scale = int(tokens[0]) if tokens and tokens[0].isdigit() else 0
            if scale < 1 or scale > 10:
                rep.error(where, f"<scale> inválido: {params}")
        elif tag == "supportedRom":
            for h in tokens:
                if not HEX40.match(h.strip()):
                    rep.warning(where, f"<supportedRom> não é sha1 de 40 hex: {h}")
        elif tag == "img":
            path = folder + params
            if not src.exists(path):
                real = src.exists_icase(path)
                if real:
                    rep.warning(where, f"<img> {params} só existe como '{real.split('/')[-1]}' — falha em Linux")
                    imgs[len(imgs)] = png_size(src.read(real))
                else:
                    rep.error(where, f"<img> não existe: {params}")
                    imgs[len(imgs)] = None
            else:
                size = png_size(src.read(path))
                if size is None:
                    rep.error(where, f"<img> não é PNG válido: {params}")
                elif scale and (size[0] % (8 * scale) or size[1] % (8 * scale)):
                    rep.warning(where, f"<img> {params} tem {size[0]}x{size[1]}, não múltiplo de {8 * scale} (scale {scale})")
                imgs[len(imgs)] = size
        elif tag == "tile":
            if version < 100:
                continue
            if len(tokens) < 6:
                rep.error(where, f"<tile> precisa de >= 6 campos, tem {len(tokens)}")
                continue
            try:
                idx = int(tokens[0])
                x, y = int(tokens[3]), int(tokens[4])
            except ValueError:
                rep.error(where, "<tile> campos numéricos inválidos")
                continue
            if idx not in imgs:
                rep.error(where, f"<tile> referencia <img> #{idx} inexistente")
            elif imgs[idx] and scale and (x + 8 * scale > imgs[idx][0] or y + 8 * scale > imgs[idx][1]):
                rep.error(where, f"<tile> em ({x},{y}) sai da imagem #{idx} ({imgs[idx][0]}x{imgs[idx][1]})")
            key = (tokens[1], tokens[2].upper(), tuple(sorted(used)))
            if key in tile_keys:
                dups.append((n, tile_keys[key]))
            else:
                tile_keys[key] = n
        elif tag == "background":
            if len(tokens) < 2:
                rep.error(where, "<background> precisa de arquivo e brilho")
                continue
            path = folder + tokens[0]
            if not src.exists(path):
                real = src.exists_icase(path)
                if real:
                    badcase.setdefault((tokens[0], real.split("/")[-1]), []).append(n)
                else:
                    missing.setdefault(tokens[0], []).append(n)
            elif png_size(src.read(path)) is None:
                rep.error(where, f"<background> não é PNG válido: {tokens[0]}")
            if len(tokens) >= 8:
                try:
                    prio = int(tokens[7])
                    if not 0 <= prio < 40:
                        rep.error(where, f"<background> prioridade fora de 0..39: {prio}")
                except ValueError:
                    rep.error(where, "<background> prioridade inválida")
        elif tag == "condition":
            if len(tokens) < 4:
                rep.error(where, "<condition> precisa de >= 4 campos")
                continue
            name, kind = tokens[0].strip(), tokens[1]
            if not name or "!" in name:
                rep.error(where, f"nome de condition inválido: '{name}'")
            if kind not in COND_TYPES:
                rep.error(where, f"tipo de condition inválido: {kind}")
                continue
            if name in conds:
                rep.warning(where, f"condition '{name}' redefinida (primeira em linha {conds[name]})")
            conds[name] = n
            cond_kinds[name] = kind
            if kind in ("tileAtPosition", "tileNearby", "spriteAtPosition", "spriteNearby"):
                if len(tokens) < 6:
                    rep.error(where, f"{kind} precisa de >= 6 campos")
                    continue
                try:
                    x, y = int(tokens[2]), int(tokens[3])
                except ValueError:
                    rep.error(where, f"{kind}: x/y inválidos")
                    continue
                if kind.endswith("AtPosition"):
                    if not (0 <= x < 256 and 0 <= y < 240):
                        rep.error(where, f"{kind} em ({x},{y}) fora da tela 256x240")
                else:
                    if abs(x) > 255 or abs(y) > 239:
                        rep.error(where, f"{kind} offset ({x},{y}) maior que a tela — nunca casa e podia derrubar o emulador (< fix de 2026-08-25)")
                    elif x % 8 or y % 8:
                        rep.info(where, f"{kind} offset ({x},{y}) não alinhado a 8 px desliga o cache desse tile")
                tile_tok = tokens[4]
                if len(tile_tok) != 32 and not re.fullmatch(r"[0-9A-Fa-f]+", tile_tok) and version >= 104:
                    rep.error(where, f"{kind}: tile deve ser 32 hex (dados) ou índice hex: {tile_tok}")
            elif kind.endswith("memoryCheck") or kind.endswith("memoryCheckConstant") or kind.startswith("ppu"):
                if version < 101:
                    rep.error(where, f"{kind} requer <ver>101+")
                if len(tokens) < 5:
                    rep.error(where, f"{kind} precisa de >= 5 campos")
        elif tag in ("bgm", "sfx"):
            need = 3 if tag == "bgm" else 3
            if len(tokens) < need:
                rep.error(where, f"<{tag}> precisa de album,track,arquivo")
                continue
            path = folder + tokens[2].strip()
            if not src.exists(path):
                rep.error(where, f"<{tag}> arquivo não existe: {tokens[2]}")
            try:
                album, track = int(tokens[0]), int(tokens[1])
                if not (0 <= album <= 255 and 0 <= track <= 255):
                    rep.error(where, f"<{tag}> album/track fora de 0..255")
            except ValueError:
                rep.error(where, f"<{tag}> album/track inválidos")
        elif tag == "patch":
            if len(tokens) != 2:
                rep.error(where, "<patch> precisa de arquivo,sha1")
                continue
            if not src.exists(folder + tokens[0]):
                rep.error(where, f"<patch> arquivo não existe: {tokens[0]}")
            if not HEX40.match(tokens[1].strip()):
                rep.error(where, f"<patch> sha1 inválido: {tokens[1]}")
            rep.info(where, "<patch> casa pelo sha1 do arquivo inteiro da ROM; outras revisões carregam o pack sem o patch (ADR-0044)")
    if version == 0:
        rep.error(rel, "<ver> ausente")
    for name, lines in sorted(missing.items(), key=lambda kv: -len(kv[1])):
        rep.error(f"{rel}:{lines[0]}", f"<background> {name} não existe — {len(lines)} entrada(s) silenciosamente descartadas pelo emulador")
    for (ref, real), lines in badcase.items():
        rep.warning(f"{rel}:{lines[0]}", f"<background> {ref} só existe como '{real}' — carrega em macOS/Windows, falha em Linux ({len(lines)} entrada(s))")
    if dups:
        sample = ", ".join(f"{n}(={first})" for n, first in dups[:5])
        rep.warning(rel, f"{len(dups)} <tile> duplicados (mesma chave/paleta/conditions); só o primeiro de cada é usado — ex.: linhas {sample}")
    for name, line in conds.items():
        pass
    rep.info(rel, f"NES hires.txt: ver {version}, scale {scale}, {len(imgs)} imagens, {len(tile_keys)} tiles, {len(conds)} conditions")


def lint_gbsms_hires(src: Source, rel: str, rep: Report):
    folder = str(PurePosixPath(rel).parent)
    folder = "" if folder == "." else folder + "/"
    text = src.text(rel)
    system = None
    scale = 1
    imgs = {}
    keys = {}
    tiles = 0
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r").strip()
        where = f"{rel}:{n}"
        if not line or line.startswith("#"):
            continue
        parsed = parse_line(line)
        if not parsed:
            rep.warning(where, f"linha não reconhecida: {line[:60]}")
            continue
        _, tag, params = parsed
        tokens = params.split(",") if params else []
        if tag not in GBSMS_TAGS:
            rep.warning(where, f"tag desconhecida para GB/SMS: <{tag}>")
            continue
        if tag == "system":
            system = params
            if system not in {"gb", "gbc", "sms", "gg"}:
                rep.error(where, f"<system> inválido: {system}")
        elif tag == "scale":
            scale = int(tokens[0]) if tokens and tokens[0].isdigit() else 0
            if scale < 1 or scale > 10:
                rep.error(where, f"<scale> inválido: {params}")
        elif tag == "img":
            path = folder + params
            if not src.exists(path):
                rep.error(where, f"<img> não existe: {params}")
                imgs[len(imgs)] = None
            else:
                imgs[len(imgs)] = png_size(src.read(path))
        elif tag == "tile":
            tiles += 1
            if len(tokens) != 7:
                rep.error(where, f"<tile> precisa de 7 campos, tem {len(tokens)}")
                continue
            try:
                idx = int(tokens[0])
                x, y = int(tokens[3]), int(tokens[4])
            except ValueError:
                rep.error(where, "<tile> campos numéricos inválidos")
                continue
            if not re.fullmatch(r"[0-9A-Fa-f]+", tokens[1]) or len(tokens[1]) % 2 or not re.fullmatch(r"[0-9A-Fa-f]*", tokens[2]):
                rep.error(where, "<tile> blobs hex inválidos")
            if idx not in imgs:
                rep.error(where, f"<tile> referencia <img> #{idx} inexistente")
            elif imgs[idx] and (x + 8 * scale > imgs[idx][0] or y + 8 * scale > imgs[idx][1]):
                rep.error(where, f"<tile> em ({x},{y}) sai da imagem #{idx}")
            if tokens[6] not in ("Y", "N"):
                rep.error(where, f"<tile> defaultTile deve ser Y/N: {tokens[6]}")
            key = (tokens[1].upper(), tokens[2].upper() if tokens[6] == "N" else "*")
            if key in keys:
                rep.warning(where, f"<tile> chave duplicada (primeira em linha {keys[key]}); a última vence")
            else:
                keys[key] = n
    if system is None:
        rep.error(rel, "<system> ausente")
    rep.info(rel, f"GB/SMS hires.txt: system {system}, scale {scale}, {len(imgs)} imagens, {tiles} tiles")


def lint_hires(src: Source, rel: str, rep: Report):
    head = src.text(rel)[:400]
    m = re.search(r"<ver>(\d+)", head)
    if m and int(m.group(1)) >= 200:
        lint_gbsms_hires(src, rel, rep)
    else:
        lint_nes_hires(src, rel, rep)


def lint_fingerprints(src: Source, rel: str, rep: Report):
    folder = str(PurePosixPath(rel).parent)
    folder = "" if folder == "." else folder + "/"
    try:
        root = json.loads(src.text(rel))
    except Exception as exc:  # noqa: BLE001
        rep.error(rel, f"JSON inválido: {exc}")
        return
    tracks = root.get("tracks") if isinstance(root, dict) else None
    if not isinstance(tracks, list):
        rep.error(rel, "'tracks' deve ser array")
        return
    ids = set()
    playable = 0
    for i, t in enumerate(tracks):
        if not isinstance(t, dict) or not isinstance(t.get("id"), str):
            rep.error(rel, f"tracks[{i}] precisa de 'id'")
            continue
        tid = t["id"]
        if tid in ids:
            rep.error(rel, f"id duplicado: {tid}")
        ids.add(tid)
        kind = t.get("kind", "bgm")
        if kind not in ("bgm", "sfx"):
            rep.error(rel, f"{tid}: kind inválido '{kind}'")
        ev = t.get("events")
        if not isinstance(ev, list) or not ev:
            rep.error(rel, f"{tid}: 'events' vazio")
        elif len(ev) < 4 and kind == "bgm":
            rep.warning(rel, f"{tid}: só {len(ev)} onset(s) — fingerprint curto demais para ser confiável")
        if t.get("midi") and not src.exists(folder + t["midi"]):
            rep.warning(rel, f"{tid}: MIDI referenciado não existe: {t['midi']}")
        ogg = f"{folder}{kind}/{tid}.ogg"
        if src.exists(ogg):
            playable += 1
    rep.info(rel, f"fingerprints: {len(tracks)} faixa(s), {playable} com OGG na mesma camada")
    if playable == 0 and tracks:
        rep.info(rel, "nenhum OGG ao lado — rode scripts/mep_render_audio.py para gerar bgm/*.ogg")


def lint_esp(src: Source, rel: str, rep: Report):
    section = None
    for n, raw in enumerate(src.text(rel).splitlines(), 1):
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if "=" not in line:
            rep.error(f"{rel}:{n}", f"linha ESP sem '=': {line[:40]}")
        elif section is None:
            rep.error(f"{rel}:{n}", "chave ESP fora de uma seção [Preset]")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    quiet = "--quiet" in argv
    target = Path(argv[1])
    if not target.exists():
        print(f"erro: {target} não existe")
        return 2
    src = Source(target)
    rep = Report()

    sections = {}
    if src.exists("pack.json"):
        sections = lint_pack_json(src, rep)
    else:
        rep.info("pack.json", "ausente — pack pela convenção de pasta (ADR-0049): identidade = nome/local")

    # camadas da convenção (também valem para packs com pack.json)
    for name, probe in PROBES.items():
        for layer, prefix in (("humana", ""), ("auto", "auto/")):
            if src.exists(prefix + probe) or (name == "audio" and src.exists(prefix + AUDIO_ALT_PROBE)):
                rep.info(prefix + probe, f"camada {layer} de '{name}' presente")
                sections.setdefault(f"{prefix}{name}", prefix + SECTION_PATHS[name])
            if name == "audio" and src.exists(prefix + AUDIO_ALT_PROBE):
                lint_fingerprints(src, prefix + AUDIO_ALT_PROBE, rep)
    if src.exists("hires.txt"):
        # HD pack HDNes solto (HdPacks/<rom>/): o hires.txt fica na raiz
        rep.info("hires.txt", "HD pack legado (hires.txt na raiz) — carregável como HdPacks/<rom>/ ou como seção textures com path \"\"")
        sections.setdefault("textures", "")
    if not sections:
        rep.error(".", "nenhuma seção encontrada (textures/hires.txt, audio/hires.txt, synth/preset.cfg, auto/...)")

    seen = set()
    for name, rel in sections.items():
        base = name.split("/")[-1]
        if base == "synth":
            if rel not in seen and src.exists(rel):
                seen.add(rel)
                lint_esp(src, rel, rep)
        else:
            hires = f"{rel}/hires.txt" if rel else "hires.txt"
            if hires not in seen and src.exists(hires):
                seen.add(hires)
                lint_hires(src, hires, rep)

    for level, where, msg in rep.items:
        if quiet and level == "info":
            continue
        print(f"{level:7s} {where}  {msg}")
    print(f"\n{rep.errors} erro(s), {rep.warnings} aviso(s) em {target}")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
