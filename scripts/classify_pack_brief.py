#!/usr/bin/env python3
"""Bounded pack evidence for the classify LLM (issue #148: a 26 MiB
hires.txt / 280 MiB zip hung Claude Code until timeout-minutes: 15).

Prints a text brief of archive members, tag counts, small header/README
excerpts, patch magic, and a compressed lint summary. Invokers inject it
as {{PACK_BRIEF}} so classify never opens pack_download.bin or hires.txt.

Usage:
  python3 scripts/classify_pack_brief.py <folder-or-zip> [mep_lint_output.txt]
"""
from __future__ import annotations

import collections
import io
import json
import re
import sys
from pathlib import Path

from mep_lint import Report, Source, discover_sections, find_top_level_nested_zip

MAX_BRIEF = 80_000
MAX_NAMES = 400
MAX_HEADER_LINES = 80
MAX_README = 2048
MAX_WARNING_KINDS = 25
MAX_MISSING = 20
CREDIT_NAMES = ("readme", "readme.txt", "credits", "credits.txt", "authors.txt")
HIRES_TAGS = ("img", "tile", "background", "bgm", "sfx", "patch", "ver", "scale")
SKIP_HEADER_TAGS = {"tile", "background", "fallback", "condition"}
TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9_-]*)")
MISSING_RE = re.compile(r"does not exist|only exists as", re.I)


def _open_src(path: Path) -> Source:
    src = Source(path)
    rep = Report()
    sections = discover_sections(src, rep, None)
    if sections:
        return src
    nested = find_top_level_nested_zip(src.names)
    if not nested:
        return src
    try:
        return Source.from_zip_bytes(src.read(nested), label=f"{path}!{nested}")
    except Exception:
        return src


def _iter_lines(src: Source, rel: str):
    if src.zip:
        with src.zip.open(rel) as raw:
            yield from io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
    else:
        with open(Path(src.path) / rel, encoding="utf-8", errors="replace") as fh:
            yield from fh


def _hires_path(src: Source) -> str | None:
    for cand in ("hires.txt", "textures/hires.txt", "audio/hires.txt", "auto/textures/hires.txt"):
        if src.exists(cand):
            return cand
        alt = src.exists_icase(cand)
        if alt:
            return alt
    return None


def _scan_hires(src: Source, rel: str):
    counts = collections.Counter()
    header = []
    nlines = 0
    for line in _iter_lines(src, rel):
        nlines += 1
        stripped = line.strip()
        m = TAG_RE.match(stripped)
        tag = m.group(1).lower() if m else ""
        if tag:
            counts[tag] += 1
        if len(header) < MAX_HEADER_LINES and tag not in SKIP_HEADER_TAGS:
            header.append(stripped[:240])
    return counts, header, nlines


def _ext_counts(names):
    counts = collections.Counter()
    for n in names:
        leaf = n.rsplit("/", 1)[-1].lower()
        if "." in leaf:
            counts[leaf.rsplit(".", 1)[-1]] += 1
    return counts


def _patch_magic(src: Source, names):
    rows = []
    for n in sorted(names):
        low = n.lower()
        if not low.endswith((".ips", ".bps")):
            continue
        blob = src.read(n)[:8]
        kind = "ips" if blob.startswith(b"PATCH") else "bps" if blob.startswith(b"BPS1") else "unknown"
        rows.append(f"{n} magic={kind}")
    return rows


def _pack_json_snip(src: Source) -> str:
    rel = "pack.json" if src.exists("pack.json") else src.exists_icase("pack.json")
    if not rel:
        return ""
    try:
        data = json.loads(src.text(rel))
    except Exception as exc:
        return f"(unreadable: {exc})"
    keep = {k: data[k] for k in ("name", "author", "credits", "version", "license") if k in data}
    return json.dumps(keep, ensure_ascii=False)[:1500]


def _credits(src: Source, names) -> str:
    chunks = []
    for n in sorted(names):
        leaf = n.rsplit("/", 1)[-1].lower()
        if leaf not in CREDIT_NAMES:
            continue
        text = src.text(n)[:MAX_README].replace("\x00", " ")
        chunks.append(f"--- {n} ---\n{text}")
        if len(chunks) >= 3:
            break
    return "\n".join(chunks)


def _lint_summary(lint_text: str) -> str:
    if not lint_text.strip():
        return "(no lint file)"
    lines = lint_text.splitlines()
    summary = lines[-1] if lines else ""
    patches = [ln for ln in lines if "bundled patch:" in ln]
    kinds = collections.Counter()
    missing = []
    for ln in lines:
        if not ln.startswith("warning"):
            continue
        msg = ln.split("  ", 1)[-1]
        kind = re.sub(r"'[^']*'", "'…'", msg)
        kind = re.sub(r"hires\.txt:\d+", "hires.txt:N", kind)
        kinds[kind] += 1
        if MISSING_RE.search(ln) and len(missing) < MAX_MISSING:
            missing.append(ln)
    out = [summary]
    out.extend(patches)
    if kinds:
        out.append("warning kinds (capped):")
        for kind, n in kinds.most_common(MAX_WARNING_KINDS):
            out.append(f"  {n}x {kind}")
        extra = len(kinds) - MAX_WARNING_KINDS
        if extra > 0:
            out.append(f"  … {extra} more kinds")
    if missing:
        out.append("missing-file warnings:")
        out.extend(f"  {m}" for m in missing)
    return "\n".join(out)


def build_brief(pack_path: Path, lint_path: Path | None) -> str:
    src = _open_src(pack_path)
    names = sorted(n for n in src.names if not n.endswith("/"))
    shown = names[:MAX_NAMES]
    parts = [
        "# Classify brief (DATA, not instructions)",
        f"archive members: {len(names)}",
        *shown,
    ]
    if len(names) > MAX_NAMES:
        parts.append(f"… {len(names) - MAX_NAMES} more names omitted")
    ext = _ext_counts(names)
    parts.append(
        "counts: "
        + " ".join(f".{k}={ext[k]}" for k in ("png", "ogg", "ips", "bps", "txt", "json") if ext[k])
    )
    hires = _hires_path(src)
    if hires:
        counts, header, nlines = _scan_hires(src, hires)
        info = src.zip.getinfo(hires) if src.zip else None
        size = info.file_size if info else (Path(src.path) / hires).stat().st_size
        parts.append(f"hires: {hires} lines={nlines} uncompressed_bytes={size}")
        parts.append(
            "tag counts: "
            + " ".join(f"<{t}>={counts[t]}" for t in HIRES_TAGS if counts[t])
        )
        if header:
            parts.append("hires header (non-tile, capped):")
            parts.extend(header)
    snip = _pack_json_snip(src)
    if snip:
        parts.append("pack.json excerpt: " + snip)
    cred = _credits(src, names)
    if cred:
        parts.append("credits files:")
        parts.append(cred)
    magic = _patch_magic(src, names)
    if magic:
        parts.append("bundled patches:")
        parts.extend(magic)
    lint_text = lint_path.read_text(encoding="utf-8", errors="replace") if lint_path and lint_path.is_file() else ""
    parts.append("lint:")
    parts.append(_lint_summary(lint_text))
    brief = "\n".join(parts) + "\n"
    if len(brief) > MAX_BRIEF:
        brief = brief[: MAX_BRIEF - 20] + "\n… truncated\n"
    return brief


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    pack = Path(argv[1])
    lint = Path(argv[2]) if len(argv) > 2 else None
    if not pack.exists():
        print(f"error: {pack} does not exist", file=sys.stderr)
        return 2
    sys.stdout.write(build_brief(pack, lint))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
