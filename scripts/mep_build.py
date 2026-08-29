#!/usr/bin/env python3
"""mep_build — author-side MEP pack builder (PRD F5.4c, ADR-0049 §2).

Builds the generated manifests of an HD/MEP pack project folder from its
editable source material, then packages it into a MEP zip:

    scripts/mep_build.py build <folder> [--scale N] [--source PATH] [--quiet]
    scripts/mep_build.py pack  <folder> [--out ZIP] [--rom ROM |
        --system S --sha1 H] [--name N] [--version V] [--author A]
        [--license L] [--quiet]
    scripts/mep_build.py rename-audio-id <folder> <old-id> <new-id>
    scripts/mep_build.py <folder>            # same as `build`

build  reads `textures/sheets/*.png` (16-column grids of `8*scale`-px
       cells; ADR-0049: cells map to tile keys through the sheet's order),
       regenerates `textures/hires.txt` pointing every tile key at the cell
       that owns it, regenerates `audio/hires.txt` from the OGGs under
       `audio/bgm/` and `audio/sfx/` (new files pick up the same track/sfx
       id as their file name, or the next free id), writes a comment header
       recording the cell -> key map, and runs the MEP linter over the
       result. The linter failing is a build failure.

       Tile keys are NOT derivable from art (an upscaled cell carries no
       2bpp pattern or NES palette index), so the keys come from a key
       source: `--source`, else `textures/hires.txt` (a prior build), else
       `auto/textures/hires.txt` (the emulator bootstrap, F5.2). The sheets
       replace the art; the keys and the header tags (ver/scale/system/
       supportedRom/options/overscan) are carried over. Background tags are
       preserved; a background PNG missing under `textures/` but present
       under `auto/textures/` is copied up (the author keeps their assets).
       <bgm>/<sfx> never live in the textures manifest — they belong to the
       audio section (MEP-v1 §2.1 rule 6), so build moves them there.

pack   writes `pack.json` at the folder root from the folder tree and the
       given identity (MEP-v1 §3.1), then zips the whole folder with a
       deterministic layout (fixed timestamps, STORED, 0o644, lexical
       order) so a rebuilt zip is byte-identical — the F6.4c fixture
       pattern. `targets` come from `--rom` (No-Intro sha1), explicit
       `--system/--sha1`, or an existing `pack.json`. The zip is linted too.

rename-audio-id  renames an enumerated `trackNN`/`sfxNN` audio id across
       `audio/fingerprints.json` (the `id` and `midi` fields), the physical
       `midi/`/`bgm/`/`sfx/` files, and any `audio/hires.txt` reference —
       the F5.4g Bloco D item 12 id-lifecycle cleanup.

Exit codes mirror mep_lint: 0 = clean, 1 = errors found, 2 = usage error.
"""

import argparse
import hashlib
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

import mep_lint

# NES hires.txt version emitted for the texture and audio manifests (ver >=
# 100 is the current HD format; 107 is what HdPackBuilder::SaveHdPack writes).
NES_VER = "107"
# Header tags carried over verbatim from the key source.
_HEADER_TAGS = ("ver", "scale", "system", "supportedRom", "options", "overscan")
_TILE_RE = re.compile(r"^(\[[^\]]*\])?<tile>(.*)$")
_BGM_RE = re.compile(r"^(\[[^\]]*\])?<bgm>(.*)$")
_SFX_RE = re.compile(r"^(\[[^\]]*\])?<sfx>(.*)$")
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)


class BuildError(Exception):
    pass


def _png_size(path: Path):
    """(width, height) from a PNG IHDR, or None when the file is not a PNG.
    Reads only the 24-byte header, so no image library is required."""
    try:
        data = path.read_bytes()[:24]
    except OSError:
        return None
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def _parse_source(lines):
    """Splits a hires.txt into header tags, ordered tile lines (condition
    prefix + raw fields), audio references (<bgm>/<sfx>), and the remaining
    body (backgrounds, patches, ...). <img> lines are dropped — the sheet
    build regenerates them."""
    header = []
    tiles = []
    audio_refs = []
    body = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("<") and s[1:].split(">", 1)[0] in _HEADER_TAGS:
            header.append(s)
            continue
        m = _TILE_RE.match(s)
        if m:
            tiles.append((m.group(1) or "", m.group(2)))
            continue
        if _BGM_RE.match(s) or _SFX_RE.match(s):
            audio_refs.append(s)
            continue
        if s.startswith("<img>"):
            continue
        body.append(s)
    return header, tiles, audio_refs, body


def _sheet_layout(path: Path, scale: int) -> int:
    """Cell count for a sheet: a 16-column grid of `8*scale` cells. Raises
    when the PNG is missing/invalid or not 16 columns (the fixed HD sheet
    geometry, HdPackBuilder::SaveHdPack)."""
    size = _png_size(path)
    if size is None:
        raise BuildError(f"{path.name}: not a valid PNG")
    cell = 8 * scale
    width, height = size
    if width % cell or height % cell:
        raise BuildError(f"{path.name}: {width}x{height} is not a multiple of {cell} (scale {scale})")
    cols = width // cell
    if cols != 16:
        raise BuildError(f"{path.name}: {width}px wide = {cols} columns, expected 16 (8*scale per cell)")
    return cols * (height // cell)


def _emit_comment(sheet_rel: str, cell: int) -> list:
    """ADR-0049: the generated hires.txt records the cell -> key map in a
    comment header, so the mapping survives edits and re-builds."""
    return [
        f"# {sheet_rel} — {cell} cell(s); cells map to tile keys through the sheet's order (ADR-0049)",
    ]


def _bgm_sfx_refs(lines):
    """Files already referenced by <bgm>/<sfx> as (kind, stem) -> (album,
    track, filename)."""
    known = {}
    for s in lines:
        for rx, kind in ((_BGM_RE, "bgm"), (_SFX_RE, "sfx")):
            m = rx.match(s)
            if not m:
                continue
            fields = [f.strip() for f in m.group(2).split(",")]
            if len(fields) >= 3:
                known[(kind, Path(fields[2]).stem)] = (fields[0], fields[1], fields[2])
    return known


def _next_free_id(ids, start=1):
    n = start
    while n in ids:
        n += 1
    return n


def _build_audio_manifest(folder: Path, system: str | None, seed: list) -> str | None:
    """Regenerates audio/hires.txt from `seed` (previous manifest or the key
    source's own <bgm>/<sfx>) plus the OGGs under audio/bgm/ and audio/sfx/
    that are not referenced yet.

    NES-only: GB/SMS/GG OGG replacement is frozen (ADR-0041) and mep_lint has
    no audio tags for the ver>=200 format, so a non-NES pack returns None.
    Seed refs whose OGG no longer exists are dropped (their track id is
    reclaimed); a digit-named OGG's id is honoured only when free, else the
    next free id is used — so the manifest never carries two <bgm>/<sfx>
    entries with the same album*256+track id.

    Returns the manifest text, or None when there is nothing to reference."""
    if system is not None and system != "nes":
        return None
    # Keep only seed refs whose OGG actually exists in the audio/ layout; a
    # dangling ref would ship an unregistered track (lint warning) and its id
    # must be reclaimed, not held.
    keep = []
    for s in seed:
        for rx, kind in ((_BGM_RE, "bgm"), (_SFX_RE, "sfx")):
            m = rx.match(s)
            if not m:
                continue
            fields = [f.strip() for f in m.group(2).split(",")]
            if len(fields) >= 3 and (folder / "audio" / Path(fields[2])).exists():
                keep.append(s)
            else:
                print(f"info: dropping {kind} ref {fields[2]} (no such file under audio/)")
            break
    kept_refs = _bgm_sfx_refs(keep)

    def scan(sub: str, kind: str):
        entries = []
        known = dict(kept_refs)
        used_ids = {int(t) for (k, _), (a, t, _) in known.items() if k == kind and a == "0" and t.isdigit()}
        d = folder / "audio" / sub
        if not d.is_dir():
            return entries
        for f in sorted(d.glob("*.ogg")):
            stem = f.stem
            if (kind, stem) in known:
                continue  # already referenced
            album = 0
            if stem.isdigit():
                track = int(stem)
                if track in used_ids:
                    print(f"info: {kind} id {track} already taken — using next free id for {f.name}")
                    track = _next_free_id(used_ids)
            else:
                track = _next_free_id(used_ids)
            used_ids.add(track)
            entries.append(f"<{kind}>{album},{track},{sub}/{f.name}")
        return entries

    keep += scan("bgm", "bgm")
    keep += scan("sfx", "sfx")
    if not keep:
        return None
    return f"<ver>{NES_VER}\n" + "\n".join(keep) + "\n"


def cmd_build(args) -> int:
    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"error: {folder} is not a directory", file=sys.stderr)
        return 2
    scale = args.scale

    # --- key source (where the tile keys come from) ---
    source = Path(args.source).resolve() if args.source else None
    if source is None:
        for cand in (folder / "textures" / "hires.txt", folder / "auto" / "textures" / "hires.txt"):
            if cand.exists():
                source = cand
                break
    if source is None or not source.is_file():
        print("error: no tile-key source; run the emulator bootstrap (auto/textures/hires.txt) or pass --source", file=sys.stderr)
        return 2

    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    header, tiles, audio_refs, body = _parse_source(lines)
    if not tiles:
        print(f"error: key source has no <tile> entries: {source}", file=sys.stderr)
        return 2

    # scale: --scale wins, else the source header's <scale>, else 2. The
    # output header always declares it (a missing <scale> would make the host
    # and lint read the manifest at scale 1 while the sheets are 8*scale).
    src_scale = None
    for h in header:
        if h.startswith("<scale>"):
            src_scale = int(h[7:].strip())
            break
    if scale is None:
        scale = src_scale if src_scale is not None else 2
    if scale < 1 or scale > 10:
        print(f"error: scale {scale} out of range (1..10)", file=sys.stderr)
        return 2

    # --- sheets: 16-column grids; cells map to keys through sheet order ---
    sheets_dir = folder / "textures" / "sheets"
    if not sheets_dir.is_dir():
        print(f"error: no textures/sheets/ folder with the author sheets: {sheets_dir}", file=sys.stderr)
        return 2
    sheets = sorted(p for p in sheets_dir.iterdir() if p.suffix.lower() == ".png")
    if not sheets:
        print(f"error: no PNG sheets in {sheets_dir}", file=sys.stderr)
        return 2
    try:
        cell_sizes = [_sheet_layout(p, scale) for p in sheets]
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    total_cells = sum(cell_sizes)
    if total_cells < len(tiles):
        print(f"error: sheets hold {total_cells} cell(s) but the key source has {len(tiles)} tile key(s)", file=sys.stderr)
        return 2
    if total_cells > len(tiles):
        print(f"info: sheets hold {total_cells} cell(s), only {len(tiles)} are referenced; trailing cells stay unused")

    offsets = []
    acc = 0
    for n in cell_sizes:
        offsets.append(acc)
        acc += n

    # --- regenerate textures/hires.txt ---
    # Header carried over with <scale> pinned to the scale actually used;
    # <ver> and <scale> are always present so the manifest can never be read
    # at a wrong scale/legacy version.
    has_ver = any(h.startswith("<ver>") for h in header)
    has_scale = any(h.startswith("<scale>") for h in header)
    out_header = []
    for h in header:
        if h.startswith("<scale>"):
            out_header.append(f"<scale>{scale}")
        else:
            out_header.append(h)
    if not has_ver:
        out_header.insert(0, f"<ver>{NES_VER}")
    if not has_scale:
        out_header.append(f"<scale>{scale}")
    cell = 8 * scale
    out_lines = list(out_header)
    for i, p in enumerate(sheets):
        rel = f"sheets/{p.name}"
        out_lines.extend(_emit_comment(rel, cell_sizes[i]))
        out_lines.append(f"<img>{rel}")
        for k in range(offsets[i], offsets[i] + cell_sizes[i]):
            if k >= len(tiles):
                break
            cond, raw = tiles[k]
            fields = raw.split(",")
            if len(fields) < 6:
                print(f"error: key source <tile> #{k} has only {len(fields)} fields: {raw}", file=sys.stderr)
                return 2
            cell_in_sheet = k - offsets[i]
            fields[0] = str(i)  # img index == sheet index (emission order)
            fields[3] = str((cell_in_sheet % 16) * cell)
            fields[4] = str((cell_in_sheet // 16) * cell)
            out_lines.append(f"{cond}<tile>{','.join(fields)}")
    out_lines.extend(body)

    textures_dir = folder / "textures"
    textures_dir.mkdir(parents=True, exist_ok=True)

    # A background PNG referenced by the body that is not under textures/
    # yet is copied up from auto/textures (the author keeps their assets).
    # The tag may carry a condition prefix ([cond]<background>...) — the only
    # form the emulator writes for captured-screen backgrounds.
    _BG_TAG = re.compile(r"^(\[[^\]]*\])?<background>")
    for b in body:
        m = _BG_TAG.match(b)
        if not m:
            continue
        name = b[m.end():].split(",")[0].strip()
        if not name:
            continue
        target = textures_dir / name
        if target.exists():
            continue
        auto_cand = folder / "auto" / "textures" / name
        if auto_cand.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(auto_cand.read_bytes())
            print(f"info: copied background {name} from auto/textures into textures/")

    hires = textures_dir / "hires.txt"
    hires.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"built {hires} — {len(tiles)} tile(s), {len(sheets)} sheet(s), scale {scale}")

    # --- regenerate audio/hires.txt (new OGGs into audio/) ---
    system = None
    for h in header:
        if h.startswith("<system>"):
            system = h[8:].strip().lower()
            break
    existing_audio = folder / "audio" / "hires.txt"
    seed = audio_refs
    if existing_audio.exists():
        seed = [l for l in existing_audio.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    if system is not None and system != "nes":
        print(f"info: audio manifest skipped — OGG replacement is NES-only (got <system>{system})")
    audio_manifest = _build_audio_manifest(folder, system, seed)
    if audio_manifest:
        (folder / "audio").mkdir(parents=True, exist_ok=True)
        (folder / "audio" / "hires.txt").write_text(audio_manifest, encoding="utf-8")
        print(f"built {folder / 'audio' / 'hires.txt'}")
    elif existing_audio.exists():
        existing_audio.unlink()
        print(f"info: removed {existing_audio} (no OGGs to reference)")

    # --- the linter is the gate ---
    return _run_lint(folder, quiet=args.quiet)


def _derive_sections(folder: Path) -> dict:
    """MEP-v1 §3.1 sections from the built tree (mirror of
    mep_recipe._derive_sections for the ADR-0049 layout)."""
    sections = {}
    if (folder / "textures" / "hires.txt").exists():
        sections["textures"] = {"path": "textures/"}
    # audio/hires.txt only: mep_lint's pack.json probe validates a section
    # against `audio/hires.txt`, not the fingerprints.json alt-probe the
    # convention scanner uses, so a fingerprint-only folder keeps no audio
    # section in pack.json (the OGGs are simply not rendered yet).
    if (folder / "audio" / "hires.txt").exists():
        sections["audio"] = {"path": "audio/"}
    if (folder / "synth" / "preset.cfg").exists():
        sections["synth"] = {"path": "synth/preset.cfg"}
    return sections


def _no_intro_sha1(rom: Path) -> str:
    """MEP-v1 §4: the NES hash covers the payload minus the 16-byte header
    and trainer, limited to the PRG+CHR size the header declares (bytes 4/5,
    NES 2.0 MSBs in byte 9) so a dump with trailing junk matches its clean
    No-Intro entry — mirroring the host's ComputeNoIntroSha1 (ADR-0044)."""
    data = rom.read_bytes()
    ext = rom.suffix.lower()
    end = len(data)
    offset = 0
    if ext == ".nes" and data[:4] == b"NES\x1a":
        offset = 16 + (512 if data[6] & 0x04 else 0)
        prg_units = data[4]
        chr_units = data[5]
        if (data[7] & 0x0C) == 0x08 and (data[9] & 0x0F) != 0x0F and (data[9] >> 4) != 0x0F:
            prg_units |= (data[9] & 0x0F) << 8
            chr_units |= (data[9] >> 4) << 8
        declared = offset + prg_units * 0x4000 + chr_units * 0x2000
        if declared > offset and declared < end:
            end = declared
    elif ext in {".sfc", ".smc", ".swc", ".fig", ".bs", ".st"} and len(data) % 1024 == 512:
        offset = 512
    return hashlib.sha1(data[offset:end]).hexdigest().upper()


def _system_for(rom: Path) -> str:
    return {
        ".nes": "nes", ".gb": "gb", ".gbc": "gbc", ".sms": "sms", ".gg": "gg",
        ".sg": "sg1000", ".sfc": "snes", ".smc": "snes",
    }.get(rom.suffix.lower(), "nes")


def cmd_pack(args) -> int:
    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"error: {folder} is not a directory", file=sys.stderr)
        return 2

    existing = {}
    pack_json = folder / "pack.json"
    if pack_json.exists():
        existing = json.loads(pack_json.read_text(encoding="utf-8"))

    if args.rom:
        rom = Path(args.rom).resolve()
        if not rom.is_file():
            print(f"error: ROM not found: {rom}", file=sys.stderr)
            return 2
        targets = [{"system": _system_for(rom), "sha1": _no_intro_sha1(rom)}]
    elif args.system and args.sha1:
        targets = [{"system": args.system, "sha1": args.sha1.upper()}]
    elif existing.get("targets"):
        targets = existing["targets"]
    else:
        print("error: need --rom, or --system + --sha1, or an existing pack.json with targets", file=sys.stderr)
        return 2

    body = {
        "mep": existing.get("mep") or "1.1.0",
        "name": args.name or existing.get("name") or folder.name,
        "version": args.version or existing.get("version") or "1.0.0",
        "license": args.license or existing.get("license") or "NOASSERTION",
        "targets": targets,
    }
    if args.author or existing.get("author"):
        body["author"] = args.author or existing["author"]
    # Carry over optional MEP-v1 §3.1 fields a re-run must not silently drop
    # (patches[] gates ROM patches at the MEP layer; ADR-0044).
    for optional in ("patches", "crc32", "md5"):
        if existing.get(optional):
            body[optional] = existing[optional]
    sections = _derive_sections(folder)
    if not sections:
        print("error: nothing to pack — no textures/, audio/ or synth/ layer with a manifest", file=sys.stderr)
        return 2
    body["sections"] = sections
    pack_json.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    out = Path(args.out).resolve() if args.out else folder.with_name(f"{body['name']}-{body['version']}.zip")
    files = {}
    for f in sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "pack.json"):
        if out == f:
            continue  # --out inside the folder must not embed a prior zip
        files[f.relative_to(folder).as_posix()] = f.read_bytes()
    # pack.json first at the root; everything else lexical (deterministic zip).
    ordered = {"pack.json": (json.dumps(body, indent=2) + "\n").encode("utf-8")}
    ordered.update(files)

    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(out, "w") as zf:
            for name, data in ordered.items():
                info = zipfile.ZipInfo(filename=name, date_time=FIXED_DATE_TIME)
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o644 << 16
                zf.writestr(info, data)
    except (UnicodeEncodeError, UnicodeDecodeError) as e:
        print(f"error: cannot zip the folder — non-UTF-8 file name: {e}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"packed {out} ({len(ordered)} entries, sha256 {digest})")

    rc = _run_lint(out, quiet=args.quiet)
    if rc != 0:
        return rc
    print(f"OK: {out} lints clean")
    return 0


def cmd_rename_audio_id(args) -> int:
    folder = Path(args.folder).resolve()
    old_id, new_id = args.old_id, args.new_id
    if not folder.is_dir():
        print(f"error: {folder} is not a directory", file=sys.stderr)
        return 2
    if not old_id or not new_id or old_id == new_id:
        print("error: need two distinct non-empty audio ids", file=sys.stderr)
        return 2

    changed = []

    # fingerprints.json: the track's `id` and its `midi` path.
    fp = folder / "audio" / "fingerprints.json"
    if fp.exists():
        data = json.loads(fp.read_text(encoding="utf-8"))
        for t in data.get("tracks", []):
            if t.get("id") != old_id:
                continue
            t["id"] = new_id
            midi = t.get("midi", "")
            t["midi"] = re.sub(r"(^|/)" + re.escape(old_id) + r"\.mid$", r"\g<1>" + new_id + ".mid", midi)
            changed.append("fingerprints.json")
        fp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # Physical files: midi/<id>.mid, bgm/<id>.ogg, sfx/<id>.ogg.
    for sub, ext in (("midi", ".mid"), ("bgm", ".ogg"), ("sfx", ".ogg")):
        src = folder / "audio" / sub / f"{old_id}{ext}"
        if not src.exists():
            continue
        dst = folder / "audio" / sub / f"{new_id}{ext}"
        if dst.exists():
            print(f"error: {dst} already exists", file=sys.stderr)
            return 1
        src.rename(dst)
        changed.append(f"audio/{sub}/{new_id}{ext}")

    # audio/hires.txt file references (bgm/<id>.ogg / sfx/<id>.ogg).
    ah = folder / "audio" / "hires.txt"
    if ah.exists():
        text = ah.read_text(encoding="utf-8")
        n = re.sub(r"(^|[,/])" + re.escape(old_id) + r"\.ogg", r"\g<1>" + new_id + ".ogg", text)
        if n != text:
            ah.write_text(n, encoding="utf-8")
            changed.append("audio/hires.txt")

    if not changed:
        print(f"info: audio id '{old_id}' not found in {folder}")
        return 0
    print(f"renamed '{old_id}' -> '{new_id}': {', '.join(changed)}")
    return 0


def _run_lint(target, quiet: bool) -> int:
    argv = ["mep_build.py", str(target)]
    if quiet:
        argv.append("--quiet")
    rc = mep_lint.main(argv)
    if rc != 0:
        print(f"error: lint failed ({target})", file=sys.stderr)
    return rc


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `mep_build.py <folder>` == `build <folder>` (PRD primary form).
    if argv and argv[0] not in ("build", "pack", "rename-audio-id", "-h", "--help"):
        argv.insert(0, "build")

    p = argparse.ArgumentParser(
        prog="mep_build.py",
        description="Author-side MEP pack builder: build textures/audio manifests from sheets + OGGs, then pack a deterministic zip.",
    )
    sub = p.add_subparsers(dest="cmd")
    b = sub.add_parser("build", help="regenerate textures/hires.txt + audio/hires.txt from textures/sheets/ and audio/")
    b.add_argument("folder")
    b.add_argument("--scale", type=int, help="cell size = 8*scale (default: the key source's <scale>, else 2)")
    b.add_argument("--source", help="hires.txt carrying the tile keys (default: textures/hires.txt, then auto/textures/hires.txt)")
    b.add_argument("--quiet", action="store_true", help="suppress lint info findings")
    b.set_defaults(func=cmd_build)
    pk = sub.add_parser("pack", help="write pack.json and zip the folder deterministically")
    pk.add_argument("folder")
    pk.add_argument("--out", help="output zip path (default: <name>-<version>.zip next to the folder)")
    pk.add_argument("--rom", help="target ROM; No-Intro sha1 is computed for it")
    pk.add_argument("--system")
    pk.add_argument("--sha1")
    pk.add_argument("--name")
    pk.add_argument("--version")
    pk.add_argument("--author")
    pk.add_argument("--license")
    pk.add_argument("--quiet", action="store_true")
    pk.set_defaults(func=cmd_pack)
    ra = sub.add_parser("rename-audio-id", help="rename an enumerated trackNN/sfxNN id across fingerprints.json + midi/bgm/sfx files")
    ra.add_argument("folder")
    ra.add_argument("old_id")
    ra.add_argument("new_id")
    ra.set_defaults(func=cmd_rename_audio_id)

    args = p.parse_args(argv)
    if not hasattr(args, "func"):
        p.print_usage()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
