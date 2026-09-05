#!/usr/bin/env python3
"""pack_generated_disclosure — MEP v1.6's root `generated` object as the
community catalog sees it (ADR-0154 §3, MEP-v1 §3.1).

A pack that declares `generated` was produced by a tool rather than drawn by
a person. That is **disclosure, never a verdict**: nothing here refuses,
labels or de-lists a pack for carrying the field. It is surfaced the way
authorship already is -- a column read off the pack itself -- because every
accepted pack auto-installs on every client (ADR-0146), and a machine repaint
listed silently beside hand-painted ones misleads whoever installs it. A
submitter who deletes the field is not detected; this is an honesty
mechanism, not a detector.

Split out of `mei_catalog_entry.py` / `generate_community_pack_catalog.py`
per ADR-0138 §35's 200-line-per-file guardrail. Stdlib only, and deliberately
a **leaf**: the Markdown constants it needs (table header, separator,
popularity note) are passed in by the caller rather than imported, so
`mei_catalog_entry` can use `generated_field` without acquiring a dependency
on `community_pack_markdown` (§24's leaf/half split).
"""
from __future__ import annotations

import re

GENERATED_UNKNOWN = "?"
GENERATED_COLUMN = "Generated"
GENERATED_EMPTY = "—"
GENERATED_NOTE = (
    "**Generated.** The column says the pack's own `pack.json` declares a\n"
    "`generated` object (MEP v1.6 §3.1): it was produced by a tool rather than\n"
    "drawn by a person, and it names the backend that made it. The pack is\n"
    "listed and installs exactly like any other — this is disclosure, so you\n"
    "know what you are installing, not a judgement about quality. Packs are not\n"
    "scanned for it; the column is empty for every pack that does not declare\n"
    "one."
)


def generated_field(mep_meta):
    """The MEP v1.6 root `generated` object as it reaches the catalog, or None.

    **Presence of the object is the label** (ADR-0154 §3), so a malformed one
    still discloses: `by`/`backend` degrade to '?' rather than making the pack
    look hand-drawn. Only the fields the catalog shows are copied, and each is
    type-checked -- mep-meta is derived from submitter-controlled content, so
    nothing from it is passed through unvalidated.
    """
    if not isinstance(mep_meta, dict):
        return None
    generated = mep_meta.get("generated")
    if not isinstance(generated, dict):
        return None
    entry = {}
    for key in ("by", "backend"):
        value = generated.get(key)
        entry[key] = value.strip() if isinstance(value, str) and value.strip() else GENERATED_UNKNOWN
    for key in ("date", "source"):
        value = generated.get(key)
        if isinstance(value, str) and value.strip():
            entry[key] = value.strip()
    scale = generated.get("scale")
    if isinstance(scale, int) and not isinstance(scale, bool) and scale > 0:
        entry["scale"] = scale
    return entry


def generated_cell(generated):
    """The column's cell: "machine (<backend>)" for a declared `generated`
    object, an em dash otherwise. The backend name comes from the pack, i.e.
    from submitter-controlled content, so it is escaped for a table cell
    exactly like every other rendered value."""
    if not generated:
        return GENERATED_EMPTY
    backend = generated.get("backend") or GENERATED_UNKNOWN
    return re.sub(r"\s+", " ", f"machine ({backend})").replace("|", "\\|").strip()


def with_generated_column(text, rows, table_header, table_sep, note=None):
    """Appends the disclosure column to an already rendered catalog.

    It works on the rendered Markdown, keyed on each row's issue URL, because
    the table renderer lives in `community_pack_markdown` and this column is
    additive to it. Every table line gets a cell, so the column count stays
    uniform; non-table lines (title, intro, notes) are untouched.
    """
    by_url = {row["url"]: generated_cell(row.get("generated")) for row in rows if row.get("url")}
    out = []
    for line in text.split("\n"):
        if line == table_header:
            out.append(f"{line} {GENERATED_COLUMN} |")
        elif line == table_sep:
            out.append(f"{line}---|")
        elif line.startswith("|"):
            # `](url)`, not a bare substring: issue 13's URL is a prefix of
            # issue 132's, and matching loosely would give one row the other's
            # disclosure.
            cell = next((c for url, c in by_url.items() if f"]({url})" in line), GENERATED_EMPTY)
            out.append(f"{line} {cell} |")
        else:
            out.append(line)
    rendered = "\n".join(out)
    if note and any(row.get("generated") for row in rows):
        rendered = rendered.replace(note, f"{note}\n\n{GENERATED_NOTE}")
    return rendered
