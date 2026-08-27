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
    chaves <tile> duplicadas, PNG com dimensão múltipla do scale;
  * hires.txt GB/SMS (<ver>200): <system>, <img> existentes, <tile> com 7 campos,
    blobs hex, chaves duplicadas.

Saída: uma linha por achado (`error|warning|info  arquivo:linha  mensagem`) e um
resumo; exit code 1 quando há erro, 0 caso contrário. O texto de cada achado é
sempre em en-US (Issues/comentários no GitHub são en-US per CLAUDE.md), mesmo
com o resto deste arquivo documentado em pt-br.

Uso: python3 scripts/mep_lint.py <pasta-ou-zip> [rom_name] [--quiet]
  rom_name (opcional): nome do ROM alvo declarado pelo submitter (ex.: "Contra
  (U) [!]"). Quando presente, habilita o fallback por nome de ROM (ADR-0120
  §3's named follow-up) além do fallback estrutural — ver
  find_fallback_subfolder_by_name.
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

# Structural fallback search limits (ADR-0120): last-priority, name-agnostic
# discovery of a pack root one or more levels below the container root (e.g.
# a release zip wrapping its payload in "Contra80s-v1.1/Contra (U) [!]/").
# Mirrored numerically (not algorithmically - see the ADR for the C++ vs
# C#/Python asymmetry) by Core::MepPack::kMepFallbackMaxDepth/
# kMepFallbackMaxEntries (C++) and MepZipValidator.FallbackMaxDepth/
# FallbackMaxEntries (C#). "Depth" is the number of '/'-separated segments
# in a normalized entry path, e.g. "Contra80s-v1.1/Contra (U) [!]/hires.txt"
# is depth 3.
FALLBACK_MAX_DEPTH = 4
FALLBACK_MAX_ENTRIES = 2000
# Every probe (human + auto/ layer) plus pack.json itself: a subfolder that
# directly holds any one of these is a candidate fallback pack root. Reuses
# PROBES/AUDIO_ALT_PROBE rather than duplicating the leaf names.
FALLBACK_SUFFIXES = ["pack.json"] + [
    variant
    for probe in list(PROBES.values()) + [AUDIO_ALT_PROBE]
    for variant in (probe, f"auto/{probe}")
]
# Bare leaf names of the probes above (ADR-0120 §3's named follow-up): what
# MepPack::FindFallbackSubfolder (C++) looks for directly under a subfolder
# segment that matches the caller-supplied ROM name. Looser than
# FALLBACK_SUFFIXES structurally (no "textures/" wrapper required) but safe
# only because the ROM-name anchor removes the ambiguity a bare basename
# would otherwise carry.
FALLBACK_PROBE_BASENAMES = {"hires.txt", "preset.cfg", "fingerprints.json"}
KNOWN_SYSTEMS = {"nes", "gb", "gbc", "sms", "gg", "sg1000", "coleco", "snes"}
NES_TAGS = {"ver", "scale", "supportedRom", "img", "tile", "background", "condition", "bgm", "sfx", "patch", "overscan", "options", "addition", "fallback"}
GBSMS_TAGS = {"ver", "scale", "system", "img", "tile", "supportedRom"}
COND_TYPES = {"tileAtPosition", "tileNearby", "spriteAtPosition", "spriteNearby", "memoryCheck", "ppuMemoryCheck", "memoryCheckConstant", "ppuMemoryCheckConstant", "frameRange", "positionCheckX", "positionCheckY", "originPositionCheckX", "originPositionCheckY"}
GLOBAL_CONDS = {"hmirror", "vmirror", "bgpriority", "sppalette0", "sppalette1", "sppalette2", "sppalette3"}
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


def _longest_matching_suffix(normalized: str):
    """Longest entry of FALLBACK_SUFFIXES that `normalized` ends with at a
    path-segment boundary ('/' + suffix), or None. Longest match wins so the
    more specific auto/ variant is preferred over the bare probe when an
    entry sits inside both (mirrors MepZipValidator.MatchCandidatePrefix in
    UI/Logic/MepZipValidator.cs — see its comment for why picking the bare
    match instead would wrongly split a pack's auto/ layer into its own,
    falsely ambiguous candidate)."""
    best = None
    for suffix in FALLBACK_SUFFIXES:
        if normalized.endswith(f"/{suffix}") and (best is None or len(suffix) > len(best)):
            best = suffix
    return best


def find_fallback_subfolder(names):
    """Pure, structural (name-agnostic) last-priority fallback (ADR-0120):
    the Python mirror of Core::MepPack::FindFallbackSubfolder (C++, matches
    by ROM name) and MepZipValidator.FindStructuralFallbackPrefix (C#,
    matches structurally like here — mep_lint has no ROM context either).
    Searches `names` (the source's full entry-path set) for a single
    subfolder that directly holds pack.json or one of PROBES/
    AUDIO_ALT_PROBE (human or auto/ layer), depth/entry-capped by
    FALLBACK_MAX_DEPTH/FALLBACK_MAX_ENTRIES. Returns (prefix, depth) for the
    one unambiguous candidate found, or None when nothing matches or more
    than one distinct candidate matches (ambiguous — fails closed rather
    than guessing, same philosophy as the C++/C# mirrors)."""
    if len(names) > FALLBACK_MAX_ENTRIES:
        return None
    candidate, candidate_depth = None, 0
    for name in sorted(names):
        # safe_rel rejects '..' segments, a leading '/', and drive letters —
        # without this guard a zip-slip-shaped entry (e.g. "../evil/textures/
        # hires.txt") would be accepted as a discovered pack root and PASS a
        # pack that BASE (and both the C++/C# mirrors, which run their own
        # traversal guards over every entry) reject. The six existing accept/
        # reject fixtures all use safe names, so this changes no legitimate
        # behavior — only closes the traversal hole.
        normalized = safe_rel(name)
        if normalized is None:
            continue
        segments = normalized.split("/")
        if len(segments) > FALLBACK_MAX_DEPTH:
            continue
        suffix = _longest_matching_suffix(normalized)
        if suffix is None:
            continue
        prefix = normalized[: -(len(suffix) + 1)]
        if not prefix:
            continue  # root-level match: already covered by the existing conventions
        if candidate is not None and candidate != prefix:
            return None
        candidate, candidate_depth = prefix, len(segments)
    return (candidate, candidate_depth) if candidate else None


def find_fallback_subfolder_by_name(names, rom_name):
    """Name-anchored last-priority fallback (ADR-0120 §3's named follow-up):
    the Python mirror of MepPack::FindFallbackSubfolder's C++ ROM-name match,
    used only when a caller supplies rom_name (the CI pipeline passes the
    Issue Form's submitter-declared game name). Unlike find_fallback_subfolder
    (structural, no ROM context), this accepts a bare probe basename
    (hires.txt/preset.cfg/fingerprints.json) directly under any subfolder
    segment matching rom_name case-insensitively — it does not require the
    textures/ or synth/ wrapper the structural check needs, because the ROM
    name anchor already makes the match unambiguous. Same depth/entry-cap
    bounds and fail-closed-on-ambiguity philosophy as find_fallback_subfolder."""
    if not rom_name or len(names) > FALLBACK_MAX_ENTRIES:
        return None
    lower_rom_name = rom_name.lower()
    candidate, candidate_depth = None, 0
    for name in sorted(names):
        normalized = safe_rel(name)
        if normalized is None:
            continue
        segments = normalized.split("/")
        if len(segments) < 2 or len(segments) > FALLBACK_MAX_DEPTH:
            continue
        if segments[-1].lower() not in FALLBACK_PROBE_BASENAMES:
            continue
        anchor = None
        for i in range(len(segments) - 2, -1, -1):
            if segments[i].lower() == lower_rom_name:
                anchor = i
                break
        if anchor is None:
            continue
        prefix = "/".join(segments[: anchor + 1])
        if candidate is not None and candidate != prefix:
            return None
        candidate, candidate_depth = prefix, len(segments)
    return (candidate, candidate_depth) if candidate else None


def scan_convention_sections(src: Source, rep: Report, sections: dict, root_prefix: str = ""):
    """Populates `sections` from the layer convention (human + auto/) under
    `root_prefix` — "" for the container root, or a fallback-discovered
    subfolder ("<prefix>/") from find_fallback_subfolder. Existing entries
    win (setdefault): a pack.json 'sections' entry is never overridden by a
    convention probe."""
    for name, probe in PROBES.items():
        for layer, layer_prefix in (("human", ""), ("auto", "auto/")):
            probe_rel = f"{root_prefix}{layer_prefix}{probe}"
            alt_rel = f"{root_prefix}{layer_prefix}{AUDIO_ALT_PROBE}"
            has_alt = name == "audio" and src.exists(alt_rel)
            if src.exists(probe_rel) or has_alt:
                rep.info(probe_rel, f"{layer} layer of '{name}' present")
                sections.setdefault(f"{layer_prefix}{name}", f"{root_prefix}{layer_prefix}{SECTION_PATHS[name]}")
            if has_alt:
                lint_fingerprints(src, alt_rel, rep)


def lint_pack_json(src: Source, rep: Report, root_prefix: str = ""):
    """Valida pack.json em `root_prefix` (raiz do container, ou o prefixo
    "<fallback>/" descoberto por find_fallback_subfolder — ADR-0120). Todos
    os paths referenciados pelo manifest (patches[].file, sections[].path)
    são resolvidos relativos a `root_prefix`, nunca à raiz do container,
    para que um pack.json descoberto via fallback seja validado por inteiro
    (MUST fields, semver, sha1s, safe_rel) em vez de servir só como marcador
    de aceite não verificado."""
    where = f"{root_prefix}pack.json"
    try:
        root = json.loads(src.text(where))
    except Exception as exc:  # noqa: BLE001
        rep.error(where, f"invalid JSON: {exc}")
        return {}
    if not isinstance(root, dict):
        rep.error(where, "root must be an object")
        return {}
    for key in ("mep", "name", "version", "license"):
        if not isinstance(root.get(key), str) or not root[key]:
            rep.error(where, f"required field missing/invalid: '{key}'")
    if isinstance(root.get("mep"), str):
        if not SEMVER.match(root["mep"]):
            rep.error(where, f"'mep' is not semver: {root['mep']}")
        elif not root["mep"].startswith("1."):
            rep.error(where, f"unsupported MEP major: {root['mep']}")
    if isinstance(root.get("version"), str) and not SEMVER.match(root["version"]):
        rep.error(where, f"'version' is not semver: {root['version']}")
    targets = root.get("targets")
    if not isinstance(targets, list) or not targets:
        rep.error(where, "'targets' must be a non-empty array")
    else:
        for i, t in enumerate(targets):
            if not isinstance(t, dict):
                rep.error(where, f"targets[{i}] must be an object")
                continue
            if t.get("system") not in KNOWN_SYSTEMS:
                rep.error(where, f"targets[{i}].system unknown: {t.get('system')}")
            if not isinstance(t.get("sha1"), str) or not HEX40.match(t["sha1"]):
                rep.error(where, f"targets[{i}].sha1 must be 40 hex digits")
    patches = root.get("patches")
    if patches is not None:
        if not isinstance(patches, list):
            rep.error(where, "'patches' must be an array")
        else:
            for i, p in enumerate(patches):
                if not isinstance(p, dict) or not isinstance(p.get("sha1"), str) or not isinstance(p.get("file"), str):
                    rep.error(where, f"patches[{i}] needs 'sha1' and 'file'")
                    continue
                if not HEX40.match(p["sha1"]):
                    rep.error(where, f"patches[{i}].sha1 must be 40 hex digits")
                rel = safe_rel(p["file"])
                if rel is None:
                    rep.error(where, f"patches[{i}].file is unsafe: {p['file']}")
                elif not src.exists(f"{root_prefix}{rel}"):
                    rep.error(where, f"patches[{i}].file does not exist: {rel}")
    sections = root.get("sections")
    found = {}
    if not isinstance(sections, dict):
        rep.error(where, "'sections' must be an object")
    else:
        for name, sec in sections.items():
            if name not in SECTION_PATHS:
                rep.info(where, f"unknown section ignored: {name}")
                continue
            if not isinstance(sec, dict) or not isinstance(sec.get("path"), str):
                rep.error(where, f"section '{name}' needs 'path'")
                continue
            rel = safe_rel(sec["path"])
            if rel is None:
                rep.error(where, f"section '{name}': unsafe path '{sec['path']}'")
                continue
            probe = rel if name == "synth" else (f"{rel}/hires.txt" if rel else "hires.txt")
            if not src.exists(f"{root_prefix}{probe}"):
                rep.error(where, f"section '{name}': '{probe}' does not exist")
            # rstrip: quando `rel` é "" (path "" == raiz do container/fallback)
            # e `root_prefix` não é vazio, a concatenação nua deixaria uma
            # barra final ("Rel-v1/Game/") que o loop em main() trataria como
            # verdadeira e duplicaria a barra ao montar "<rel>/hires.txt" —
            # o hires.txt daquela seção nunca seria encontrado/lintado e o
            # pack seria aceito sem essa camada ter sido validada.
            found[name] = f"{root_prefix}{rel}".rstrip("/")
        if not found:
            rep.error(where, "'sections' needs textures/audio/synth")
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
            rep.warning(where, f"unrecognized line: {line[:60]}")
            continue
        used, tag, params = parsed
        tokens = params.split(",") if params else []
        if tag not in NES_TAGS:
            rep.warning(where, f"unknown tag <{tag}>")
            continue
        for c in used:
            base = c[1:] if c.startswith("!") else c
            if base not in conds and base not in GLOBAL_CONDS:
                rep.error(where, f"condition '{base}' used before being defined (or nonexistent)")
        if tag == "ver":
            version = int(tokens[0]) if tokens and tokens[0].isdigit() else 0
            if version < 100:
                rep.warning(where, f"<ver>{version} is legacy format (pre-100)")
        elif tag == "scale":
            scale = int(tokens[0]) if tokens and tokens[0].isdigit() else 0
            if scale < 1 or scale > 10:
                rep.error(where, f"<scale> invalid: {params}")
        elif tag == "supportedRom":
            for h in tokens:
                if not HEX40.match(h.strip()):
                    rep.warning(where, f"<supportedRom> is not a 40-hex sha1: {h}")
        elif tag == "img":
            path = folder + params
            if not src.exists(path):
                real = src.exists_icase(path)
                if real:
                    rep.warning(where, f"<img> {params} only exists as '{real.split('/')[-1]}' — fails on Linux")
                    imgs[len(imgs)] = png_size(src.read(real))
                else:
                    rep.error(where, f"<img> does not exist: {params}")
                    imgs[len(imgs)] = None
            else:
                size = png_size(src.read(path))
                if size is None:
                    rep.error(where, f"<img> is not a valid PNG: {params}")
                elif scale and (size[0] % (8 * scale) or size[1] % (8 * scale)):
                    rep.warning(where, f"<img> {params} is {size[0]}x{size[1]}, not a multiple of {8 * scale} (scale {scale})")
                imgs[len(imgs)] = size
        elif tag == "tile":
            if version < 100:
                continue
            if len(tokens) < 6:
                rep.error(where, f"<tile> needs >= 6 fields, has {len(tokens)}")
                continue
            try:
                idx = int(tokens[0])
                x, y = int(tokens[3]), int(tokens[4])
            except ValueError:
                rep.error(where, "<tile> invalid numeric fields")
                continue
            if idx not in imgs:
                rep.error(where, f"<tile> references nonexistent <img> #{idx}")
            elif imgs[idx] and scale and (x + 8 * scale > imgs[idx][0] or y + 8 * scale > imgs[idx][1]):
                rep.error(where, f"<tile> at ({x},{y}) is outside image #{idx} ({imgs[idx][0]}x{imgs[idx][1]})")
            key = (tokens[1], tokens[2].upper(), tuple(sorted(used)))
            if key in tile_keys:
                dups.append((n, tile_keys[key]))
            else:
                tile_keys[key] = n
        elif tag == "background":
            if len(tokens) < 2:
                rep.error(where, "<background> needs file and brightness")
                continue
            path = folder + tokens[0]
            if not src.exists(path):
                real = src.exists_icase(path)
                if real:
                    badcase.setdefault((tokens[0], real.split("/")[-1]), []).append(n)
                else:
                    missing.setdefault(tokens[0], []).append(n)
            elif png_size(src.read(path)) is None:
                rep.error(where, f"<background> is not a valid PNG: {tokens[0]}")
            if len(tokens) >= 8:
                try:
                    prio = int(tokens[7])
                    if not 0 <= prio < 40:
                        rep.error(where, f"<background> priority out of 0..39: {prio}")
                except ValueError:
                    rep.error(where, "<background> invalid priority")
        elif tag == "condition":
            if len(tokens) < 4:
                rep.error(where, "<condition> needs >= 4 fields")
                continue
            name, kind = tokens[0].strip(), tokens[1]
            if not name or "!" in name:
                rep.error(where, f"invalid condition name: '{name}'")
            if kind not in COND_TYPES:
                rep.error(where, f"invalid condition type: {kind}")
                continue
            if name in conds:
                rep.warning(where, f"condition '{name}' redefined (first at line {conds[name]})")
            conds[name] = n
            if kind in ("tileAtPosition", "tileNearby", "spriteAtPosition", "spriteNearby"):
                if len(tokens) < 6:
                    rep.error(where, f"{kind} needs >= 6 fields")
                    continue
                try:
                    x, y = int(tokens[2]), int(tokens[3])
                except ValueError:
                    rep.error(where, f"{kind}: invalid x/y")
                    continue
                if kind.endswith("AtPosition"):
                    if not (0 <= x < 256 and 0 <= y < 240):
                        rep.error(where, f"{kind} at ({x},{y}) outside the 256x240 screen")
                else:
                    if abs(x) > 255 or abs(y) > 239:
                        rep.error(where, f"{kind} offset ({x},{y}) larger than the screen — never matches and used to crash the emulator (< 2026-08-25 fix)")
                    elif x % 8 or y % 8:
                        rep.info(where, f"{kind} offset ({x},{y}) not aligned to 8px disables this tile's cache")
                tile_tok = tokens[4]
                if len(tile_tok) != 32 and not re.fullmatch(r"[0-9A-Fa-f]+", tile_tok) and version >= 104:
                    rep.error(where, f"{kind}: tile must be 32 hex (data) or a hex index: {tile_tok}")
            elif kind.endswith("memoryCheck") or kind.endswith("memoryCheckConstant") or kind.startswith("ppu"):
                if version < 101:
                    rep.error(where, f"{kind} requires <ver>101+")
                if len(tokens) < 5:
                    rep.error(where, f"{kind} needs >= 5 fields")
        elif tag in ("bgm", "sfx"):
            need = 3 if tag == "bgm" else 3
            if len(tokens) < need:
                rep.error(where, f"<{tag}> needs album,track,file")
                continue
            path = folder + tokens[2].strip()
            if not src.exists(path):
                rep.error(where, f"<{tag}> file does not exist: {tokens[2]}")
            try:
                album, track = int(tokens[0]), int(tokens[1])
                if not (0 <= album <= 255 and 0 <= track <= 255):
                    rep.error(where, f"<{tag}> album/track out of 0..255")
            except ValueError:
                rep.error(where, f"<{tag}> invalid album/track")
        elif tag == "patch":
            if len(tokens) != 2:
                rep.error(where, "<patch> needs file,sha1")
                continue
            if not src.exists(folder + tokens[0]):
                rep.error(where, f"<patch> file does not exist: {tokens[0]}")
            if not HEX40.match(tokens[1].strip()):
                rep.error(where, f"<patch> invalid sha1: {tokens[1]}")
            rep.info(where, "<patch> matches by the whole ROM file's sha1; other revisions load the pack without the patch (ADR-0044)")
    if version == 0:
        rep.error(rel, "<ver> missing")
    for name, lines in sorted(missing.items(), key=lambda kv: -len(kv[1])):
        rep.error(f"{rel}:{lines[0]}", f"<background> {name} does not exist — {len(lines)} entry/entries silently dropped by the emulator")
    for (ref, real), lines in badcase.items():
        rep.warning(f"{rel}:{lines[0]}", f"<background> {ref} only exists as '{real}' — loads on macOS/Windows, fails on Linux ({len(lines)} entry/entries)")
    if dups:
        sample = ", ".join(f"{n}(={first})" for n, first in dups[:5])
        rep.warning(rel, f"{len(dups)} duplicate <tile>(s) (same key/palette/conditions); only the first of each is used — e.g. lines {sample}")
    for name, line in conds.items():
        pass
    rep.info(rel, f"NES hires.txt: ver {version}, scale {scale}, {len(imgs)} images, {len(tile_keys)} tiles, {len(conds)} conditions")


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
            rep.warning(where, f"unrecognized line: {line[:60]}")
            continue
        _, tag, params = parsed
        tokens = params.split(",") if params else []
        if tag not in GBSMS_TAGS:
            rep.warning(where, f"unknown tag for GB/SMS: <{tag}>")
            continue
        if tag == "system":
            system = params
            if system not in {"gb", "gbc", "sms", "gg"}:
                rep.error(where, f"<system> invalid: {system}")
        elif tag == "scale":
            scale = int(tokens[0]) if tokens and tokens[0].isdigit() else 0
            if scale < 1 or scale > 10:
                rep.error(where, f"<scale> invalid: {params}")
        elif tag == "img":
            path = folder + params
            if not src.exists(path):
                rep.error(where, f"<img> does not exist: {params}")
                imgs[len(imgs)] = None
            else:
                imgs[len(imgs)] = png_size(src.read(path))
        elif tag == "tile":
            tiles += 1
            if len(tokens) != 7:
                rep.error(where, f"<tile> needs 7 fields, has {len(tokens)}")
                continue
            try:
                idx = int(tokens[0])
                x, y = int(tokens[3]), int(tokens[4])
            except ValueError:
                rep.error(where, "<tile> invalid numeric fields")
                continue
            if not re.fullmatch(r"[0-9A-Fa-f]+", tokens[1]) or len(tokens[1]) % 2 or not re.fullmatch(r"[0-9A-Fa-f]*", tokens[2]):
                rep.error(where, "<tile> invalid hex blobs")
            if idx not in imgs:
                rep.error(where, f"<tile> references nonexistent <img> #{idx}")
            elif imgs[idx] and (x + 8 * scale > imgs[idx][0] or y + 8 * scale > imgs[idx][1]):
                rep.error(where, f"<tile> at ({x},{y}) is outside image #{idx}")
            if tokens[6] not in ("Y", "N"):
                rep.error(where, f"<tile> defaultTile must be Y/N: {tokens[6]}")
            key = (tokens[1].upper(), tokens[2].upper() if tokens[6] == "N" else "*")
            if key in keys:
                rep.warning(where, f"<tile> duplicate key (first at line {keys[key]}); the last one wins")
            else:
                keys[key] = n
    if system is None:
        rep.error(rel, "<system> missing")
    rep.info(rel, f"GB/SMS hires.txt: system {system}, scale {scale}, {len(imgs)} images, {tiles} tiles")


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
        rep.error(rel, f"invalid JSON: {exc}")
        return
    tracks = root.get("tracks") if isinstance(root, dict) else None
    if not isinstance(tracks, list):
        rep.error(rel, "'tracks' must be an array")
        return
    ids = set()
    playable = 0
    for i, t in enumerate(tracks):
        if not isinstance(t, dict) or not isinstance(t.get("id"), str):
            rep.error(rel, f"tracks[{i}] needs 'id'")
            continue
        tid = t["id"]
        if tid in ids:
            rep.error(rel, f"duplicate id: {tid}")
        ids.add(tid)
        kind = t.get("kind", "bgm")
        if kind not in ("bgm", "sfx"):
            rep.error(rel, f"{tid}: invalid kind '{kind}'")
        ev = t.get("events")
        if not isinstance(ev, list) or not ev:
            rep.error(rel, f"{tid}: 'events' is empty")
        elif len(ev) < 4 and kind == "bgm":
            rep.warning(rel, f"{tid}: only {len(ev)} onset(s) — fingerprint too short to be reliable")
        if t.get("midi") and not src.exists(folder + t["midi"]):
            rep.warning(rel, f"{tid}: referenced MIDI does not exist: {t['midi']}")
        ogg = f"{folder}{kind}/{tid}.ogg"
        if src.exists(ogg):
            playable += 1
    rep.info(rel, f"fingerprints: {len(tracks)} track(s), {playable} with an OGG in the same layer")
    if playable == 0 and tracks:
        rep.info(rel, "no OGG alongside — run scripts/mep_render_audio.py to generate bgm/*.ogg")


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
            rep.error(f"{rel}:{n}", f"ESP line without '=': {line[:40]}")
        elif section is None:
            rep.error(f"{rel}:{n}", "ESP key outside a [Preset] section")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    quiet = "--quiet" in argv
    positional = [a for a in argv[1:] if not a.startswith("--")]
    target = Path(positional[0])
    rom_name = positional[1] if len(positional) > 1 else None
    if not target.exists():
        print(f"error: {target} does not exist")
        return 2
    src = Source(target)
    rep = Report()

    sections = {}
    if src.exists("pack.json"):
        sections = lint_pack_json(src, rep)
    else:
        rep.info("pack.json", "absent — pack via folder convention (ADR-0049): identity = name/location")

    # camadas da convenção (também valem para packs com pack.json)
    scan_convention_sections(src, rep, sections)
    if src.exists("hires.txt"):
        # HD pack HDNes solto (HdPacks/<rom>/): o hires.txt fica na raiz
        rep.info("hires.txt", "Legacy HD pack (hires.txt at the root) — loadable as HdPacks/<rom>/ or as a textures section with path \"\"")
        sections.setdefault("textures", "")

    if not sections:
        # ADR-0120: nenhuma convenção casou na raiz — última tentativa antes
        # de rejeitar: procura um subdiretório estrutural (ver
        # find_fallback_subfolder) que sozinho contenha a convenção; se isso
        # falhar e um rom_name tiver sido passado, tenta o fallback por nome
        # de ROM (ADR-0120 §3's named follow-up, find_fallback_subfolder_by_name).
        fallback = find_fallback_subfolder(src.names)
        fallback_kind = "structural" if fallback else None
        if not fallback and rom_name:
            fallback = find_fallback_subfolder_by_name(src.names, rom_name)
            fallback_kind = "ROM-name" if fallback else None
        if fallback:
            fb_prefix, fb_depth = fallback
            rep.info(fb_prefix, f"{fallback_kind} fallback (ADR-0120): pack root discovered at '{fb_prefix}' (depth {fb_depth})")
            fb_root = f"{fb_prefix}/"
            if src.exists(f"{fb_root}pack.json"):
                # pack.json foi o próprio marcador que tornou este subdiretório
                # candidato (FALLBACK_SUFFIXES) — precisa ser lintado por
                # inteiro aqui, senão um manifest malformado/inseguro seria
                # aceito sem nunca ser validado (só a presença de suas seções
                # via scan_convention_sections abaixo).
                sections = lint_pack_json(src, rep, root_prefix=fb_root)
            scan_convention_sections(src, rep, sections, root_prefix=fb_root)
            if src.exists(f"{fb_root}hires.txt"):
                # espelha o branch de HD pack legado (linha ~628, hires.txt na
                # raiz do container) sob o prefixo descoberto: o mesmo layout
                # solto pode estar embrulhado dentro do fallback (ex.: zip com
                # só "Rel-v1/Game/synth/preset.cfg" + "Rel-v1/Game/hires.txt",
                # sem pack.json e sem textures/hires.txt) — sem este espelho a
                # camada textures fica muda: nunca é lintada nem reportada.
                rep.info(f"{fb_root}hires.txt", "Legacy HD pack (hires.txt at the fallback root) — loadable as a textures section with path \"\"")
                sections.setdefault("textures", fb_prefix)

    if not sections:
        rep.error(".", "no section found (textures/hires.txt, audio/hires.txt, synth/preset.cfg, auto/...)")

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
    print(f"\n{rep.errors} error(s), {rep.warnings} warning(s) in {target}")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
