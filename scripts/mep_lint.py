#!/usr/bin/env python3
"""mep_lint — offline pack validation (F5.1; roadmap: docs/roadmap/PRD-mesence-enhancement-ecosystem.md).

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
       python3 scripts/mep_lint.py --content-id <folder-or-zip> [rom_name]
       python3 scripts/mep_lint.py --list-games <folder-or-zip> [rom_name]
       python3 scripts/mep_lint.py [--content-id] --root <prefix> <folder-or-zip> [rom_name]
  rom_name (optional): target ROM name declared by the submitter (e.g.
  "Contra (U) [!]"). When present, enables the ROM-name fallback (ADR-0120
  §3's named follow-up) in addition to the structural fallback — see
  find_fallback_subfolder_by_name.

  --list-games (ADR-0143): print the distinct game pack roots the container
  holds as one "root<tab>game" line per root (root "" == the container
  root), so the pipeline can split a multi-game container into one pack and
  one issue per game. game is the pack.json targets[0].name when present,
  else the candidate subfolder name.
  --root <prefix> (ADR-0143): lint exactly the pack at <prefix> (a split
  pass's own root), skipping the structural fallback — the caller already
  resolved the root via --list-games.

  --content-id (ADR-0139/P.1): run the same pack-root discovery, then print
  only the tree content_id (hex SHA-256 over the canonical manifest of the
  discovered root — scripts/mep_content_id.py) and exit. Exit 1 when no
  section is found (content_id undefined), so the CI workflow can record the
  hash in mep-meta only for packs discovery actually resolved.

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

import mep_content_id  # ADR-0139 tree content_id of the discovered pack root
import pack_id_rules  # ADR-0140 source (1): SLUG shape of the MEP root `id`

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
NES_TAGS = {"ver", "scale", "system", "supportedRom", "img", "tile", "background", "condition", "bgm", "sfx", "patch", "overscan", "options", "addition", "fallback"}
GBSMS_TAGS = {"ver", "scale", "system", "img", "tile", "supportedRom"}
COND_TYPES = {"tileAtPosition", "tileNearby", "spriteAtPosition", "spriteNearby", "memoryCheck", "ppuMemoryCheck", "memoryCheckConstant", "ppuMemoryCheckConstant", "frameRange", "positionCheckX", "positionCheckY", "originPositionCheckX", "originPositionCheckY"}
GLOBAL_CONDS = {"hmirror", "vmirror", "bgpriority", "sppalette0", "sppalette1", "sppalette2", "sppalette3"}
# HdPackLoader::ProcessBackgroundTag (Core/NES/HdPacks/HdPackLoader.cpp)
# attaches a <background> condition when its type is TileAtPos/SpriteAtPos/
# TileNearby/SpriteNearby/MemoryCheck/MemoryCheckConstant/FrameRange/
# PositionCheckX/Y (Nearby is evaluated at (0,0) so it matches the pack's
# stored tile offset, same as TileAtPos). Anything else logs "Invalid
# condition type for background" and drops only that condition — the
# <background> entry itself still loads. GLOBAL_CONDS names (hmirror/
# vmirror/bgpriority/sppaletteN) stay tile-only: they dereference the
# per-tile pointer, which is null when a background is chosen.
BG_ALLOWED_KINDS = {
    "tileAtPosition", "spriteAtPosition", "tileNearby", "spriteNearby",
    "memoryCheck", "ppuMemoryCheck", "memoryCheckConstant",
    "ppuMemoryCheckConstant", "frameRange", "positionCheckX", "positionCheckY",
}
HDPACK_BOOL_TRUE = {"Y", "YES", "TRUE", "1"}
HDPACK_BOOL_FALSE = {"N", "NO", "FALSE", "0"}
HDPACK_BOOL = HDPACK_BOOL_TRUE | HDPACK_BOOL_FALSE
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
        # Lower-cased paths of the ROM patches the manifest actually wires
        # (`<patch>` tags, pack.json `patches[]`), filled while linting so
        # scan_bundled_patches can tell a wired patch from one that merely
        # rides along in the archive (ADR-0148 amending ADR-0144).
        self.wired_patches = set()

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


def find_fallback_subfolder_candidates(names):
    """Every distinct subfolder prefix in `names` that directly holds a
    fallback probe (pack.json, a textures/audio/synth probe — human or auto/
    layer — or a bare legacy probe basename with no wrapper, ADR-0121),
    bounded by the ADR-0120 depth/entry caps. Sorted; the single-candidate
    case is exactly what `find_fallback_subfolder` returns, and N>1 distinct
    candidates is the ADR-0143 multi-game trigger — each distinct pack root
    is a distinct game pack, which the single-root fallback fails closed on
    rather than guessing. The `safe_rel` guard keeps the same zip-slip
    protection the single-root fallback applies to every entry."""
    if len(names) > FALLBACK_MAX_ENTRIES:
        return []
    depths = {}
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
        depths[prefix] = len(segments)
    return [(prefix, depths[prefix]) for prefix in sorted(depths)]


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
    ROM-name-anchored instead of gaining this same structural widening;
    ADR-0143: a caller that needs the N>1 multi-game case reads it from
    find_fallback_subfolder_candidates instead)."""
    candidates = find_fallback_subfolder_candidates(names)
    return candidates[0] if len(candidates) == 1 else None


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


def _root_is_pack(src: Source) -> bool:
    """Whether the container root itself is a pack root (MEP pack.json, a
    textures/audio/synth convention probe — human or auto/ layer — or a
    legacy hires.txt at the root). Mirrors discover_sections' root-level
    checks, so discover_game_roots and discover_sections never disagree
    about which roots a container owns."""
    return (
        src.exists("pack.json")
        or src.exists("hires.txt")
        or src.exists(AUDIO_ALT_PROBE)
        or any(src.exists(p) or src.exists(f"auto/{p}") for p in PROBES.values())
    )


def _root_game_name(src: Source, root_prefix: str):
    """The ADR-0143 game identity for a pack root at `root_prefix`: the first
    MEP target's `name` when the root has a pack.json (MEP-v1 §3.1, targets[]
    is the pack's declared game identity), else the subfolder's last segment
    (a legacy HD pack's own folder name). None when neither names one."""
    if src.exists(f"{root_prefix}pack.json"):
        try:
            root = json.loads(src.text(f"{root_prefix}pack.json"))
        except Exception:  # noqa: BLE001 -- a malformed manifest names no game
            root = None
        if isinstance(root, dict):
            targets = root.get("targets")
            if isinstance(targets, list) and targets and isinstance(targets[0], dict):
                name = targets[0].get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
    if root_prefix:
        return root_prefix.rstrip("/").rsplit("/", 1)[-1]
    return None


def find_nested_game_zips(src: Source):
    """ADR-0143 last-resort for a container shaped like a GitHub repo archive:
    the wrapper folder (e.g. `<Repo>-<branch>/`) holds subfolders that each
    contain a game `.zip` rather than an extracted pack, so no direct
    subfolder candidate exists (LiQuiDzGit/HDnes stores its games this way).
    Scans every `.zip` under a subfolder (depth-capped by FALLBACK_MAX_DEPTH,
    entry-capped by FALLBACK_MAX_ENTRIES), opens it in memory, and returns
    (zip_path, game) for each zip that IS a pack root when opened —
    `_root_is_pack` on the inner Source plus `_root_game_name` (pack.json
    targets[0].name, else the zip's own subfolder name). A zip that is not a
    pack (a docs/bonus zip with no hires.txt/pack.json at its root) is not a
    candidate — same fail-closed discipline as every other discovery path.

    The returned prefix is the exact `.zip` path, not its parent subfolder:
    the per-game zip the pipeline builds by filtering on that prefix then
    contains ONLY that zip, so a subfolder holding several valid variants
    (Duck_Hunt's Audio/NEA/HDV1.1) yields one game with one concrete zip —
    never a per-game zip leaking all variants (which would trip the
    exactly-one-top-level-zip fallback and lint as "no section found").
    One root per subfolder: the first by sorted name wins — a subfolder is
    one game, one slot, one issue (ADR-0143), never N issues for the same
    game."""
    if len(src.names) > FALLBACK_MAX_ENTRIES:
        return []
    by_subfolder = {}
    for name in sorted(src.names):
        normalized = safe_rel(name)
        if normalized is None or not normalized.lower().endswith(".zip"):
            continue
        segments = normalized.split("/")
        if len(segments) < 2 or len(segments) > FALLBACK_MAX_DEPTH:
            continue
        outer = "/".join(segments[:-1])
        if outer in by_subfolder:
            continue  # first (sorted) valid zip for this subfolder already won
        try:
            inner = Source.from_zip_bytes(src.read(normalized), label=f"{src.path}!{normalized}")
        except (zipfile.BadZipFile, OSError, ValueError):
            continue  # not a real zip — not a candidate
        if not _root_is_pack(inner):
            continue
        game = _root_game_name(inner, "") or segments[-2] or None
        by_subfolder[outer] = (normalized, game)
    return list(by_subfolder.values())


def discover_game_roots(src: Source, rom_name):
    """The distinct game pack roots the container holds (ADR-0143): one
    ("", game) entry when the container root is itself a pack, else one
    (prefix, game) entry per fallback subfolder candidate. `game` is
    _root_game_name (pack.json targets[0].name, else the subfolder name),
    falling back to the submitter-declared rom_name when structurally
    unnamed. When neither the root nor any direct subfolder candidate
    resolves (a repo-archive shape whose games are nested zips, not
    extracted packs), falls back to find_nested_game_zips. The pipeline
    splits a result with N>1 roots into N packs and N sibling issues; a
    single root keeps the existing one-issue flow."""
    if _root_is_pack(src):
        return [("", _root_game_name(src, "") or rom_name)]
    direct = find_fallback_subfolder_candidates(src.names)
    if direct:
        return [(prefix, _root_game_name(src, f"{prefix}/") or prefix.rsplit("/", 1)[-1])
                for prefix, _ in direct]
    return [(prefix, game) for prefix, game in find_nested_game_zips(src)]


def discover_scoped(src: Source, rep: Report, root_prefix):
    """Discovery scoped to one known pack root (ADR-0143 split pass — the
    mirror of discover_sections' fallback branch): lint pack.json at
    `<root_prefix>/` when present, then the convention layers and the legacy
    hires.txt-at-root mirror, with NO structural fallback because the caller
    already resolved which root this pass owns."""
    sections = {}
    src.root_prefix = root_prefix
    rp = f"{root_prefix}/"
    if src.exists(f"{rp}pack.json"):
        sections = lint_pack_json(src, rep, root_prefix=rp)
    else:
        rep.info("pack.json", "absent — pack via folder convention (ADR-0049): identity = name/location")
    scan_convention_sections(src, rep, sections, root_prefix=rp)
    if src.exists(f"{rp}hires.txt"):
        rep.info(f"{rp}hires.txt", "Legacy HD pack (hires.txt at the pack root) — loadable as HdPacks/<rom>/ or as a textures section with path \"\"")
        sections.setdefault("textures", root_prefix)
    return sections


def discover_sections(src: Source, rep: Report, rom_name):
    """Runs every pack-root discovery path (existing conventions, then the
    ADR-0120 structural and ROM-name fallbacks, in priority order) against
    `src` and returns the resulting `sections` dict (empty when nothing
    matched). Factored out of main() so it can be run a second time against
    a nested .zip discovered by find_top_level_nested_zip (issue #19) with
    no duplicated logic between the two passes."""
    sections = {}
    # Track the discovered pack root so compute_content_id can hash exactly
    # the files under it (ADR-0139: files outside the root — e.g. sibling
    # folders in a container that wrapped the pack one level deeper — are
    # NOT part of the pack's content_id). "" = the container root; the
    # fallback branches below set the subfolder prefix when they win.
    src.root_prefix = ""
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
            src.root_prefix = fb_prefix
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


def compute_content_id(src: Source) -> str:
    """Tree content_id (ADR-0139/P.1) of the discovered pack root: the files
    under `src.root_prefix` (set by discover_sections — "" = the container
    root, a subfolder after a fallback win), hashed by the normative
    scripts/mep_content_id.py. Raises ValueError when a path is too long; the
    caller decides whether that fails the pack (--content-id mode) or merely
    reports it (a plain lint keeps working without the hash)."""
    prefix = getattr(src, "root_prefix", "")
    entries = []
    for name in sorted(src.names):
        rel = safe_rel(name)
        if rel is None:
            continue
        if prefix:
            if not rel.startswith(f"{prefix}/"):
                continue
            rel = rel[len(prefix) + 1:]
        entries.append((rel, src.read(name)))
    return mep_content_id.compute_tree_content_id(entries)


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
    for key in ("mep", "name", "version"):
        if not isinstance(root.get(key), str) or not root[key]:
            rep.error(where, f"required field missing/invalid: '{key}'")
    # MEP-v1 §3.1: `license` is SHOULD since v1.1 — absent reads as NOASSERTION.
    if "license" not in root:
        rep.warning(where, "'license' not declared (hosts read it as NOASSERTION)")
    elif not isinstance(root["license"], str) or not root["license"]:
        rep.error(where, "'license' must be a non-empty string when present")
    # MEP-v1 §3.1 (v1.4): `id` is SHOULD — the pack's product identity
    # (pack_id, ADR-0140 source (1)). Hosts MUST never fail a load on it: a
    # non-matching value is ignored as if absent and the catalog derives a
    # pack_id from the fallbacks (owner/repo x game, issue-n,
    # local:<container>). So every `id` finding is a warning, never an error
    # (a lint error would flip the CI verdict to `invalid`, contradicting the
    # spec). The check mirrors pack_id_rules.mep_id_from_meta: strip +
    # lowercase, then match SLUG.
    if "id" not in root:
        rep.warning(where, "'id' not declared (a catalog fallback pack_id — owner/repo x game, issue-n or local:<container> — will be used; ADR-0140)")
    elif not isinstance(root["id"], str):
        rep.warning(where, "'id' must be a string; ignored (a catalog fallback pack_id will be used; MEP-v1 §3.1)")
    else:
        folded = root["id"].strip().lower()
        if not pack_id_rules.SLUG.match(folded):
            rep.warning(where, f"'id' {root['id']!r} is not a slug [a-z0-9][a-z0-9-]{{2,63}}; ignored (a catalog fallback pack_id will be used; MEP-v1 §3.1)")
        elif folded != root["id"]:
            rep.warning(where, f"'id' {root['id']!r} should be written lowercase (hosts compare it as {folded!r}; MEP-v1 §3.1)")
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
            # MEI v1.1 §2.3: rom.sha1 MAY be absent regardless of kind — an
            # entry without one is listable/installable but not hash-matchable.
            sha1 = t.get("sha1")
            if sha1 is not None and (not isinstance(sha1, str) or not HEX40.match(sha1)):
                rep.error(where, f"targets[{i}].sha1 must be 40 hex digits")
    patches = root.get("patches")
    if patches is not None:
        if not isinstance(patches, list):
            rep.error(where, "'patches' must be an array")
        else:
            for i, p in enumerate(patches):
                if not isinstance(p, dict) or not isinstance(p.get("file"), str):
                    rep.error(where, f"patches[{i}] needs 'file'")
                    continue
                rep.wired_patches.add((root_prefix + p["file"]).lower())
                # MEI v1.1 §2.3: patch ROM sha1 MAY be absent (an un-hashed
                # patch is applied on user override with a warning).
                p_sha1 = p.get("sha1")
                if p_sha1 is not None and (not isinstance(p_sha1, str) or not HEX40.match(p_sha1)):
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
        # Windows-authored hires.txt files commonly use backslash path
        # separators; normalize before any path lookup so file existence
        # checks match HdPackLoader.cpp, which normalizes the same way
        # when parsing a pack definition line (both must agree, or a pack
        # that loads fine could still fail lint, or vice versa).
        params = params.replace("\\", "/")
        tokens = [t.strip() for t in params.split(",")] if params else []
        if tag not in NES_TAGS:
            rep.warning(where, f"unknown tag <{tag}>")
            continue
        for c in used:
            base = c[1:] if c.startswith("!") else c
            if base not in conds and base not in GLOBAL_CONDS:
                rep.warning(where, f"condition '{base}' not found — dropped from this entry's condition list, file parse continues (HdPackLoader::ParseConditionString)")
            elif tag == "background" and (base in GLOBAL_CONDS or cond_kinds.get(base) not in BG_ALLOWED_KINDS):
                kind_label = cond_kinds.get(base, base)
                rep.warning(where, f"condition '{base}' ({kind_label}) is not valid in <background> — HdPackLoader::ProcessBackgroundTag drops this condition (logs 'Invalid condition type for background'); the background entry still loads")
        if tag == "ver":
            version = int(tokens[0]) if tokens and tokens[0].isdigit() else 0
            if version < 100:
                rep.warning(where, f"<ver>{version} is legacy format (pre-100)")
        elif tag == "scale":
            scale = int(tokens[0]) if tokens and tokens[0].isdigit() else 0
            if scale < 1 or scale > 10:
                rep.error(where, f"<scale> invalid: {params}")
        elif tag == "system":
            # Optional in NES packs (HdPackLoader ignores unknown tags); when
            # present it must agree with the format branch (ADR-0136 §5).
            if params.strip().lower() != "nes":
                rep.error(where, f"<system> invalid for a NES hires.txt: {params} (expected nes)")
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
            if len(tokens) > 4 and version >= 106:
                try:
                    prio = int(tokens[4])
                    if not 0 <= prio < 40:
                        rep.warning(where, f"<background> priority out of 0..39: {prio} — entry is dropped, not registered (HdPackLoader::ProcessBackgroundTag checkConstraint)")
                except ValueError:
                    rep.error(where, f"<background> priority is not an integer: {tokens[4]!r}")
            elif len(tokens) > 4 and tokens[4].upper() not in HDPACK_BOOL:
                rep.warning(where, f"<background> field 5 (priority flag, pre-106 format) should be Y/N: {tokens[4]!r} — treated as N (HdPackLoader::ParseBooleanValue)")
            if len(tokens) > 7 and tokens[7] not in ("Alpha", "Add", "Subtract"):
                rep.warning(where, f"<background> unknown blend mode {tokens[7]!r} — falls back to Alpha (HdPackLoader::ProcessBackgroundTag)")
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
                real = src.exists_icase(path)
                if real:
                    # Case-mismatched but present (Windows-authored pack; a
                    # ref like `ogg/STAGE1.ogg` stored as `ogg/stage1.ogg`).
                    # The loader resolves it, so the track IS available on
                    # macOS/Windows — mirroring the <img> rule, only Linux
                    # would fail to load it.
                    rep.warning(where, f"<{tag}> {tokens[2]} only exists as '{real.split('/')[-1]}' — loads on macOS/Windows, fails on Linux (HdPackLoader::ProcessSoundTrack)")
                else:
                    rep.warning(where, f"<{tag}> file does not exist: {tokens[2]} — track/effect never registered, unavailable at playback, load continues (HdPackLoader::ProcessSoundTrack)")
            try:
                album, track = int(tokens[0]), int(tokens[1])
                if not (0 <= album <= 255 and 0 <= track <= 255):
                    rep.error(where, f"<{tag}> album/track out of 0..255")
            except ValueError:
                rep.error(where, f"<{tag}> invalid album/track")
        elif tag == "patch":
            # A patch filename may itself contain a comma (real packs do:
            # `Ice Climber (USA, Europe).bps`) — naive comma-splitting would
            # mis-parse it as three tokens and wrongly flag `<patch> needs
            # file,sha1`. The sha1 is the LAST comma-separated token; the
            # filename is everything before it, commas included.
            m = re.match(r"^(.*),\s*([0-9A-Fa-f]{40})\s*$", params)
            if not m:
                rep.error(where, "<patch> needs file,sha1")
                continue
            patch_file, patch_sha1 = m.group(1).strip(), m.group(2)
            rep.wired_patches.add((folder + patch_file).lower())
            if not src.exists(folder + patch_file):
                real = src.exists_icase(folder + patch_file)
                if real:
                    # Case-mismatched but present (Windows-authored pack; a
                    # ref like `MUSICPATCH.ips` stored as `MusicPatch.ips`).
                    # The patch IS applied on macOS/Windows — count it as
                    # present so the ADR-0144 audio exception can redeem the
                    # section; only Linux would fail to load it.
                    rep.warning(where, f"<patch> {patch_file} only exists as '{real.split('/')[-1]}' — loads on macOS/Windows, fails on Linux (HdPackLoader::ProcessPatchTag)")
                else:
                    rep.warning(where, f"<patch> file does not exist: {patch_file} — patch not applied, load continues (HdPackLoader::ProcessPatchTag)")
            rep.info(where, "<patch> matches by the whole-file sha1 or the No-Intro PRG+CHR sha1 (ADR-0044); other revisions load the pack without the patch")
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
        # See the matching normalization in lint_nes_hires above.
        params = params.replace("\\", "/")
        tokens = [t.strip() for t in params.split(",")] if params else []
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
            default_flag = tokens[6].upper()
            if default_flag not in HDPACK_BOOL:
                rep.error(where, f"<tile> defaultTile must be Y/N: {tokens[6]}")
            key = (tokens[1].upper(), tokens[2].upper() if default_flag in HDPACK_BOOL_FALSE else "*")
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
        #F5.4g Block C item 8 (ADR-0134 Option A): optional `loop` point in PCM
        #samples at the OGG's own rate. Absence is fine (loops the whole file);
        #a present value must be a non-negative number. Bounds vs the OGG length
        #are not checked here - OggReader clamps an out-of-range value to 0.
        loop = t.get("loop")
        if loop is not None and (not isinstance(loop, (int, float)) or isinstance(loop, bool) or loop < 0):
            rep.error(rel, f"{tid}: 'loop' must be a non-negative number of PCM samples, not {loop!r}")
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


def scan_bundled_patches(src: Source, rep: Report):
    """ADR-0144: report the .ips/.bps ROM patches actually present in the
    archive (including inside a nested zip the caller already unwrapped into
    src). The classifier's ADR-0144 audio exception hinges on "the zip
    bundles a .ips/.bps ROM patch that IS present" — and it cannot see
    inside a nested zip from a byte-read of the outer archive, so the
    linter, which DOES recurse into nested zips, is the authority. Since
    ADR-0148 (amending ADR-0144) presence alone is not enough: the patch
    must also be wired — referenced by a `<patch>` line or a pack.json
    `patches[]` entry — or the host never applies it and the extract-audio
    flow (ADR-0135) never runs. An unreferenced patch riding along in the
    zip is exactly the LiQuiDz repo shape that made #128 (1942) contribute
    nothing, so each line says which case it is. Reported at `info` level
    but printed even under --quiet (see main), so the classifier always
    sees it."""
    seen = set()
    wired_bases = {w.rsplit("/", 1)[-1] for w in rep.wired_patches}
    for name in sorted(src.names):
        lower = name.lower()
        if not lower.endswith((".ips", ".bps")) or lower in seen:
            continue
        seen.add(lower)
        if lower in rep.wired_patches or lower.rsplit("/", 1)[-1] in wired_bases:
            rep.info("pack", f"bundled patch: {name} (present, wired — applied on load)")
        else:
            rep.info("pack", f"bundled patch: {name} (present, NOT wired — no <patch> line / patches[] entry, never applied; ADR-0148)")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    quiet = "--quiet" in argv
    content_id_only = "--content-id" in argv
    list_games = "--list-games" in argv
    root_prefix = None
    positional = []
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--root" and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            root_prefix = argv[i + 1].rstrip("/")
            i += 2
            continue
        if not arg.startswith("--"):
            positional.append(arg)
        i += 1
    target = Path(positional[0])
    rom_name = positional[1] if len(positional) > 1 else None
    if not target.exists():
        print(f"error: {target} does not exist")
        return 2
    src = Source(target)
    rep = Report()

    if list_games:
        # ADR-0143: enumerate the distinct game pack roots so the pipeline
        # can split a multi-game container into one pack and one issue per
        # game. A single top-level .zip wraps one pack one level deeper —
        # mirror the issue #19 last resort before concluding no game exists.
        roots = discover_game_roots(src, rom_name)
        if not roots:
            nested_name = find_top_level_nested_zip(src.names)
            if nested_name:
                try:
                    nested_src = Source.from_zip_bytes(src.read(nested_name), label=f"{target}!{nested_name}")
                except zipfile.BadZipFile as exc:
                    rep.info(nested_name, f"single top-level .zip entry found but could not be opened as a zip ({exc}) — skipping nested-zip fallback")
                else:
                    roots = discover_game_roots(nested_src, rom_name)
        for prefix, game in roots:
            print(f"{prefix}\t{game or ''}")
        return 0

    if root_prefix is not None:
        # ADR-0143 split pass: lint exactly the pack at <root_prefix> (no
        # structural fallback — the pipeline already resolved the root).
        sections = discover_scoped(src, rep, root_prefix)
    else:
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

    if content_id_only:
        if not sections:
            return 1
        try:
            print(compute_content_id(src))
            return 0
        except ValueError as exc:
            print(f"error: content_id not computed: {exc}", file=sys.stderr)
            return 2

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

    scan_bundled_patches(src, rep)

    for level, where, msg in rep.items:
        # The bundled-patch lines are the ADR-0144 signal the classifier
        # needs, so they survive --quiet (which otherwise strips `info`).
        if quiet and level == "info" and not (where == "pack" and msg.startswith("bundled patch:")):
            continue
        print(f"{level:7s} {where}  {msg}")
    print(f"\n{rep.errors} error(s), {rep.warnings} warning(s) in {target}")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
