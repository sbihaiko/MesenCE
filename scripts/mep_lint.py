#!/usr/bin/env python3
"""mep_lint — offline pack validation (F5.1, docs/roadmap/plano-execucao-F5.md).

Accepts a directory or a .zip and checks, without running the emulator:

  * pack.json (optional under the folder convention — ADR-0049): MUST fields
    of the MEP-v1 spec, semver, hashes, safe paths, patches[] (ADR-0044);
  * convention layout: textures/hires.txt, audio/hires.txt, synth/preset.cfg
    and the same layers under auto/;
  * NES hires.txt (HDNes): known tags, referenced files that exist
    (<img>, <background>, <bgm>, <sfx>, <patch>), <condition> with a valid
    type, *AtPosition coordinates within 256x240, *Nearby offsets within the
    screen range (the off-by-one that used to crash the emulator is reported
    here), duplicate <tile> keys, PNG dimensions that are a multiple of scale;
  * GB/SMS hires.txt (<ver>200): <system>, existing <img>, <tile> with 7
    fields, hex blobs, duplicate keys.

Output: one line per finding (`error|warning|info  file:line  message`) and a
summary; exit code 1 when there is an error, 0 otherwise. Each finding's text
is always in en-US (GitHub Issues/comments are en-US per CLAUDE.md).

Usage: python3 scripts/mep_lint.py <folder-or-zip> [rom_name] [--quiet]
  rom_name (optional): target ROM name declared by the submitter (e.g.
  "Contra (U) [!]"). When present, enables the ROM-name fallback (ADR-0120
  §3's named follow-up) in addition to the structural fallback — see
  find_fallback_subfolder_by_name.

  Last resort (issue #19): if no convention or fallback finds anything and
  the container has exactly one .zip directly at its root, that .zip is
  unpacked in memory and discovery runs again from scratch against its
  contents — see find_top_level_nested_zip/discover_sections.
"""
import io
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
# Bare leaf names of the probes above: what MepPack::FindFallbackSubfolder
# (C++) looks for directly under a subfolder segment that matches the
# caller-supplied ROM name (ADR-0120 §3's named follow-up) — no "textures/"
# wrapper required, safe there because the ROM-name anchor removes the
# ambiguity a bare basename would otherwise carry. ADR-0121 additionally
# folds these into FALLBACK_SUFFIXES below, so the *structural* (name-
# agnostic) fallback accepts them too: a classic Mesen HD pack (hires.txt at
# a wrapper folder's own root, no textures/ wrapper at all) whose wrapper is
# named after a release/repo rather than the ROM — e.g. a raw GitHub
# `/archive/refs/heads/<branch>.zip` download's `<Repo>-<branch>/hires.txt`
# — has no ROM-name segment to anchor on, so only the structural path can
# ever discover it. Same fail-closed-on-ambiguity/depth/entry-cap discipline
# as every other candidate in FALLBACK_SUFFIXES; see community-pack issues
# #46 (PepCodes/HDNes-Graphics-Pac) and #47 (ModernRetroDesign/ZII-mesen),
# both real fixtures with this exact shape.
FALLBACK_PROBE_BASENAMES = {"hires.txt", "preset.cfg", "fingerprints.json"}
# Every probe (human + auto/ layer) plus pack.json itself, plus (ADR-0121)
# the bare legacy probe basenames with no textures/audio/synth wrapper: a
# subfolder that directly holds any one of these is a candidate fallback
# pack root. Reuses PROBES/AUDIO_ALT_PROBE/FALLBACK_PROBE_BASENAMES rather
# than duplicating the leaf names.
FALLBACK_SUFFIXES = (
    ["pack.json"]
    + [
        variant
        for probe in list(PROBES.values()) + [AUDIO_ALT_PROBE]
        for variant in (probe, f"auto/{probe}")
    ]
    + sorted(FALLBACK_PROBE_BASENAMES)
)
KNOWN_SYSTEMS = {"nes", "gb", "gbc", "sms", "gg", "sg1000", "coleco", "snes"}
NES_TAGS = {"ver", "scale", "supportedRom", "img", "tile", "background", "condition", "bgm", "sfx", "patch", "overscan", "options", "addition", "fallback"}
GBSMS_TAGS = {"ver", "scale", "system", "img", "tile", "supportedRom"}
COND_TYPES = {"tileAtPosition", "tileNearby", "spriteAtPosition", "spriteNearby", "memoryCheck", "ppuMemoryCheck", "memoryCheckConstant", "ppuMemoryCheckConstant", "frameRange", "positionCheckX", "positionCheckY", "originPositionCheckX", "originPositionCheckY"}
GLOBAL_CONDS = {"hmirror", "vmirror", "bgpriority", "sppalette0", "sppalette1", "sppalette2", "sppalette3"}
# HdPackLoader::ProcessBackgroundTag (Core/NES/HdPacks/HdPackLoader.cpp) only
# pushes a <background>'s HdPackCondition into BackgroundInfo.Conditions when
# its GetConditionType() is one of TileAtPos/SpriteAtPos/MemoryCheck/
# MemoryCheckConstant/FrameRange; anything else logs "Invalid condition type
# for background" and drops that <background> entry (same non-fatal
# checkConstraint()+return path as a missing PNG file). tileNearby/
# spriteNearby and every GLOBAL_CONDS name (hmirror/vmirror/bgpriority/
# sppaletteN, each its own distinct condition type) are valid in <tile> but
# not <background> — confirmed live against Contra80s-v1.1 (a `tileNearby`
# condition named 'norris8' loads fine in <tile> at line 413 but is rejected
# at lines 417/420 when reused in <background>).
BG_ALLOWED_KINDS = {"tileAtPosition", "spriteAtPosition", "memoryCheck", "ppuMemoryCheck", "memoryCheckConstant", "ppuMemoryCheckConstant", "frameRange"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
HEX40 = re.compile(r"^[0-9A-Fa-f]{40}$")


class Source:
    """Uniformizes folder and zip: listing, byte and text reading. Also
    accepts a .zip already in memory via from_zip_bytes, without writing
    anything to disk — used by the ADR-0120 last resort that unpacks a .zip
    nested inside the downloaded container (issue #19: a real pack wrapped
    one level deeper, e.g. inside a Google Drive zip alongside unrelated
    bonus content)."""

    def __init__(self, path: Path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if path.is_file() else None
        self._init_names()

    @classmethod
    def from_zip_bytes(cls, data: bytes, label: str):
        src = cls.__new__(cls)
        src.path = label
        src.zip = zipfile.ZipFile(io.BytesIO(data))
        src._init_names()
        return src

    def _init_names(self):
        if self.zip:
            self.names = {n.replace("\\", "/") for n in self.zip.namelist()}
        else:
            self.names = {p.relative_to(self.path).as_posix() for p in self.path.rglob("*") if p.is_file()}

    def exists(self, rel: str) -> bool:
        return rel in self.names

    def exists_icase(self, rel: str):
        """Real name when the file exists only under a different
        capitalization (macOS/Windows load it, Linux does not), else None."""
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
    """Pure, structural (name-agnostic) last-priority fallback (ADR-0120,
    extended by ADR-0121): the Python mirror of
    MepZipValidator.FindStructuralFallbackPrefix (C#, matches structurally
    like here — mep_lint has no ROM context either). Searches `names` (the
    source's full entry-path set) for a single subfolder that directly holds
    pack.json, one of PROBES/AUDIO_ALT_PROBE (human or auto/ layer), or
    (ADR-0121) a bare FALLBACK_PROBE_BASENAMES leaf with no textures/audio/
    synth wrapper — depth/entry-capped by FALLBACK_MAX_DEPTH/
    FALLBACK_MAX_ENTRIES. Returns (prefix, depth) for the one unambiguous
    candidate found, or None when nothing matches or more than one distinct
    candidate matches (ambiguous — fails closed rather than guessing, same
    philosophy as the C#/C++ mirrors — see ADR-0121 for why the C++ runtime
    loader's own MepPack::FindFallbackSubfolder deliberately stays
    ROM-name-anchored instead of gaining this same structural widening)."""
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


_TRAILING_TAG_RE = re.compile(r"\s*[\(\[][^()\[\]]*[\)\]]\s*$")
_SEPARATOR_RE = re.compile(r"[_-]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_rom_core_name(name):
    """Strips trailing (region)/[flag] tags repeatedly, folds underscores/
    hyphens to spaces, collapses repeated whitespace, and lowercases, so a
    submitter's human-typed game name ("Contra (USA)") can anchor against
    both the pack's internal goodtools/no-intro-style ROM name
    ("Contra (U) [!]") and a repo/folder-naming convention that uses
    underscores or hyphens where a human types a space (e.g. HDnes's
    "Super_Mario_Bros/" vs. a submitter's "Super Mario Bros") -- exact-string
    matching alone practically never bridges either gap, since submitters
    describe the game, not the ROM filename or folder-naming convention."""
    prev = None
    stripped = name.strip()
    while stripped != prev:
        prev = stripped
        stripped = _TRAILING_TAG_RE.sub("", stripped)
    folded = _SEPARATOR_RE.sub(" ", stripped)
    return _WHITESPACE_RE.sub(" ", folded).strip().lower()


def find_fallback_subfolder_by_name(names, rom_name):
    """Name-anchored last-priority fallback (ADR-0120 §3's named follow-up):
    the Python mirror of MepPack::FindFallbackSubfolder's C++ ROM-name match,
    used only when a caller supplies rom_name (the CI pipeline passes the
    Issue Form's submitter-declared game name). Unlike find_fallback_subfolder
    (structural, no ROM context), this accepts a bare probe basename
    (hires.txt/preset.cfg/fingerprints.json) directly under any subfolder
    segment matching rom_name case-insensitively — it does not require the
    textures/ or synth/ wrapper the structural check needs, because the ROM
    name anchor already makes the match unambiguous. Falls back to a
    region/flag-tag-normalized comparison when the exact-lowercase match
    fails, since the Issue Form's rom_name is a human description, not the
    ROM's actual internal filename. Same depth/entry-cap bounds and
    fail-closed-on-ambiguity philosophy as find_fallback_subfolder."""
    if not rom_name or len(names) > FALLBACK_MAX_ENTRIES:
        return None
    lower_rom_name = rom_name.lower()
    normalized_rom_name = normalize_rom_core_name(rom_name)
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
            segment_lower = segments[i].lower()
            if segment_lower == lower_rom_name:
                anchor = i
                break
            if len(normalized_rom_name) >= 2 and normalize_rom_core_name(segments[i]) == normalized_rom_name:
                anchor = i
                break
        if anchor is None:
            continue
        prefix = "/".join(segments[: anchor + 1])
        if candidate is not None and candidate != prefix:
            return None
        candidate, candidate_depth = prefix, len(segments)
    return (candidate, candidate_depth) if candidate else None


def find_top_level_nested_zip(names):
    """Last-resort discovery (issue #19), tried only after every existing
    convention and both fallbacks (structural, ROM-name) already found
    nothing: when the container has exactly one entry that sits directly at
    its root (no '/') and ends in ".zip", that entry is a candidate for
    being the real pack, wrapped one level deeper than any current
    discovery path looks (e.g. a Google Drive export whose top level is
    "Bonus1/", "Bonus2/", "RealPack.zip", "readme.txt"). Returns that
    entry's name, or None when there is no such entry or more than one
    (ambiguous — same fail-closed philosophy as the structural/ROM-name
    fallbacks: guessing wrong here would silently lint unrelated bonus
    content instead of the real pack)."""
    candidates = []
    for name in names:
        normalized = safe_rel(name)
        if normalized is None or "/" in normalized:
            continue
        if normalized.lower().endswith(".zip"):
            candidates.append(normalized)
    return candidates[0] if len(candidates) == 1 else None


def discover_sections(src: Source, rep: Report, rom_name):
    """Runs every pack-root discovery path (existing conventions, then the
    ADR-0120 structural and ROM-name fallbacks, in priority order) against
    `src` and returns the resulting `sections` dict (empty when nothing
    matched). Factored out of main() so it can be run a second time against
    a nested .zip discovered by find_top_level_nested_zip (issue #19) with
    no duplicated logic between the two passes."""
    sections = {}
    if src.exists("pack.json"):
        sections = lint_pack_json(src, rep)
    else:
        rep.info("pack.json", "absent — pack via folder convention (ADR-0049): identity = name/location")

    # convention layers (also apply to packs that have a pack.json)
    scan_convention_sections(src, rep, sections)
    if src.exists("hires.txt"):
        # HD pack HDNes solto (HdPacks/<rom>/): o hires.txt fica na raiz
        rep.info("hires.txt", "Legacy HD pack (hires.txt at the root) — loadable as HdPacks/<rom>/ or as a textures section with path \"\"")
        sections.setdefault("textures", "")

    if not sections:
        # ADR-0120 (extended by ADR-0121): no convention matched at the root
        # — last attempt before rejecting: look for a structural subfolder
        # (see find_fallback_subfolder) that alone holds the convention or a
        # bare legacy probe basename (hires.txt/preset.cfg/fingerprints.json,
        # no wrapper); if that fails and a rom_name was passed, try the
        # ROM-name fallback (ADR-0120 §3's named follow-up,
        # find_fallback_subfolder_by_name).
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
                # pack.json was itself the marker that made this subdirectory
                # a candidate (FALLBACK_SUFFIXES) — it needs to be linted in
                # full here, otherwise a malformed/unsafe manifest would be
                # accepted without ever being validated (only its sections'
                # presence, via scan_convention_sections below).
                sections = lint_pack_json(src, rep, root_prefix=fb_root)
            scan_convention_sections(src, rep, sections, root_prefix=fb_root)
            if src.exists(f"{fb_root}hires.txt"):
                # mirrors the legacy HD pack branch (line ~628, hires.txt at
                # the container root) under the discovered prefix: the same
                # loose layout can be wrapped inside the fallback (e.g. a zip
                # with only "Rel-v1/Game/synth/preset.cfg" + "Rel-v1/Game/
                # hires.txt", no pack.json and no textures/hires.txt) —
                # without this mirror the textures layer stays mute: never
                # linted nor reported.
                rep.info(f"{fb_root}hires.txt", "Legacy HD pack (hires.txt at the fallback root) — loadable as a textures section with path \"\"")
                sections.setdefault("textures", fb_prefix)

    return sections


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
    """Validates pack.json at `root_prefix` (the container root, or the
    "<fallback>/" prefix discovered by find_fallback_subfolder — ADR-0120).
    Every path referenced by the manifest (patches[].file, sections[].path)
    is resolved relative to `root_prefix`, never to the container root, so
    that a pack.json discovered via fallback is validated in full (MUST
    fields, semver, sha1s, safe_rel) instead of just serving as an
    unverified acceptance marker."""
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
            # rstrip: when `rel` is "" (path "" == container/fallback root)
            # and `root_prefix` is not empty, the bare concatenation would
            # leave a trailing slash ("Rel-v1/Game/") that the loop in main()
            # would treat as truthy and double the slash when building
            # "<rel>/hires.txt" — that section's hires.txt would never be
            # found/linted and the pack would be accepted without that layer
            # ever having been validated.
            found[name] = f"{root_prefix}{rel}".rstrip("/")
        if not found:
            rep.error(where, "'sections' needs textures/audio/synth")
    return found


def parse_line(line: str):
    """Returns (conds, tag, params) from a `[c1&c2]<tag>params` line."""
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
    cond_kinds = {}
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
                rep.warning(where, f"condition '{base}' not found — dropped from this entry's condition list, file parse continues (HdPackLoader::ParseConditionString)")
            elif tag == "background" and (base in GLOBAL_CONDS or cond_kinds.get(base) not in BG_ALLOWED_KINDS):
                kind_label = cond_kinds.get(base, base)
                rep.warning(where, f"condition '{base}' ({kind_label}) is not valid in <background> — HdPackLoader::ProcessBackgroundTag silently drops this entry (logs 'Invalid condition type for background' and falls back to the original NES graphics for it, no crash)")
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
                rep.warning(where, f"<tile> at ({x},{y}) is outside image #{idx} ({imgs[idx][0]}x{imgs[idx][1]}) — renders as fully transparent, load continues (HdPackTileInfo::Init bounds check)")
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
            cond_kinds[name] = kind
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
                rep.warning(where, f"<{tag}> file does not exist: {tokens[2]} — track/effect never registered, unavailable at playback, load continues (HdPackLoader::ProcessSoundTrack)")
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
                rep.warning(where, f"<patch> file does not exist: {tokens[0]} — patch not applied, load continues (HdPackLoader::ProcessPatchTag)")
            if not HEX40.match(tokens[1].strip()):
                rep.error(where, f"<patch> invalid sha1: {tokens[1]}")
            rep.info(where, "<patch> matches by the whole ROM file's sha1; other revisions load the pack without the patch (ADR-0044)")
    if version == 0:
        rep.error(rel, "<ver> missing")
    for name, lines in sorted(missing.items(), key=lambda kv: -len(kv[1])):
        rep.warning(f"{rel}:{lines[0]}", f"<background> {name} does not exist — {len(lines)} entry/entries dropped, falls back to original graphics (HdPackLoader::ProcessBackgroundTag)")
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

    sections = discover_sections(src, rep, rom_name)

    if not sections:
        # Issue #19: absolute last resort, tried only once every convention
        # and both ADR-0120 fallbacks above already found nothing — the pack
        # may be wrapped one level deeper inside a single top-level .zip
        # (e.g. a Google Drive export bundling the real pack.zip alongside
        # unrelated bonus folders). Unwraps in memory and re-runs the exact
        # same discovery against the nested zip's own content.
        nested_name = find_top_level_nested_zip(src.names)
        if nested_name:
            try:
                nested_src = Source.from_zip_bytes(src.read(nested_name), label=f"{target}!{nested_name}")
            except zipfile.BadZipFile as exc:
                rep.info(nested_name, f"single top-level .zip entry found but could not be opened as a zip ({exc}) — skipping nested-zip fallback")
            else:
                rep.info(nested_name, "nested-zip fallback (issue #19): re-running discovery inside this single top-level .zip entry")
                src = nested_src
                sections = discover_sections(src, rep, rom_name)

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
