#!/usr/bin/env python3
"""generate_community_pack_catalog.py — regenerates docs/community-packs.md
and docs/community-packs.json.

The board/accepted-item fetch lives in `mei_catalog_fetch` (ADR-0138 §35
split: this module orchestrates, that one fetches, `mei_catalog_entry`
assembles, `community_pack_markdown` renders the Game / Console / Author /
Date / 👍 table, to which `pack_generated_disclosure` adds ADR-0154 §3's
"Generated" column: a pack that declares `generated` in its pack.json says
so next to Author -- disclosure, never a verdict). P.2 (ADR-0140/0141, PRD §3.3/§3.6): each item becomes a
`_candidate` with its resolved pack_id/content_id/origin/version/
validated_at/votes; `pack_id_rules.select_catalog_rows` keeps one live row
per pack_id (the §3.6 slot winner), drops byte-duplicates (same content_id)
and foreign-origin claims. The final ordering lives in
`community_pack_markdown.render_table`, which `sorted(`s the rows by
`thumbs_up` — the table is ranked by community 👍 votes, most-voted-first,
no usage telemetry; the 👍 cell links to the submission issue for voting.
Re-exports build_pack_entry/mei_entry_conforms/normalized_rom_sha1/
STATUS_MEP_COMPLETO/STATUS_HD_PARCIAL (ADR-0138 §24).

stdlib only. Usage: python3 scripts/generate_community_pack_catalog.py
"""
import json
import sys
from datetime import date
from pathlib import Path

import community_pack_markdown as markdown
import pack_generated_disclosure as disclosure  # ADR-0154 §3 "Generated" column
import mep_errata  # ADR-0152 known-missing declarations, keyed on the artifact sha256
import mei_catalog_entry as entry_mod
import pack_id_rules
import rom_target
from mei_catalog_entry import (  # noqa: F401 -- facade re-export (ADR-0138 §24)
    STATUS_HD_PARCIAL,
    STATUS_MEP_COMPLETO,
    build_pack_entry,
    mei_entry_conforms,
    normalized_rom_sha1,
)
from mei_catalog_fetch import (  # noqa: E402
    fetch_accepted_items,
    fetch_issue_details,
    fetch_mep_meta,
    issue_form_fields,
    item_issue_number,
    item_pack_hash,
    item_pack_url,
    item_rom_sha1,
    item_status,
)

ACCEPTED_STATUSES = {STATUS_HD_PARCIAL, STATUS_MEP_COMPLETO}
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "community-packs.md"
JSON_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "community-packs.json"


def _warn(message):  # non-fatal per-item warning; never aborts the whole run
    print(f"WARNING: {message}", file=sys.stderr)


def _candidate(item):
    """One accepted item with its P.2 identity resolved (pack_id/content_id/
    origin/version/validated_at/votes); None without an issue number. The
    §3.3/§3.6 filter runs here BEFORE any row or MEI entry renders."""
    issue_number = item_issue_number(item)
    if issue_number is None:
        _warn("an accepted board item has no issue number; skipping it (cannot resolve pack_id).")
        return None
    details = fetch_issue_details(issue_number)
    form = issue_form_fields(details)
    mep_meta = fetch_mep_meta(issue_number)
    form["credits"] = (mep_meta or {}).get("author") or form["credits"]
    # For a split submission the primary issue's body still carries the
    # original multi-game "Target game/ROM and region" line, but mep-meta
    # records the per-game identity the split assigned it (ADR-0143). Prefer
    # that so the catalog's Game column shows the individual game, not the
    # whole submission's line.
    meta_game = (mep_meta or {}).get("game")
    if isinstance(meta_game, str) and meta_game.strip():
        form["game"] = meta_game.strip()
    pack_url, pack_hash = item_pack_url(item), item_pack_hash(item)
    version, _ = entry_mod.pack_version_fields((mep_meta or {}).get("recipe"))
    author = ((details.get("author") or {}).get("login") or "")
    return {"issue_number": issue_number, "status": item_status(item), "form": form,
            "details": details, "mep_meta": mep_meta, "pack_url": pack_url,
            "pack_hash": pack_hash, "rom_sha1": item_rom_sha1(item),
            "pack_id": pack_id_rules.resolve_pack_id(pack_url, mep_meta, issue_number)[0],
            "content_id": (mep_meta or {}).get("content_id"), "version": version,
            "validated_at": (mep_meta or {}).get("validated_at"),
            "origin": pack_id_rules.pack_origin(pack_url, author),
            #ADR-0154 §3: read off the pack, like `author` -- never off the
            #submitter, and never turned into a verdict.
            "generated": disclosure.generated_field(mep_meta),
            "votes": markdown.thumbs_up_count(details)}


def _render(c):
    """(markdown_row, mei_entry_or_None) for a KEPT candidate; the entry is
    None on a non-conformant Pack URL/Hash/system or a conform failure.
    `rom.sha1` comes from the board's "ROM SHA1" field when the submitter/
    pipeline populated it; otherwise the catalog game name is resolved
    against the versioned No-Intro map (rom_target) so the auto-install can
    match a clean No-Intro dump of the target game (ADR-0138 §2.3). An
    unresolved game keeps `rom: {}` (listable/installable, not hash-matchable).
    """
    issue, status, form, details = c["issue_number"], c["status"], c["form"], c["details"]
    system = (form["console"] or "?").strip().lower()
    #ADR-0152: the table marks a row whose artifact carries reviewed
    #known-missing declarations, so a reader is never told a pack is complete
    #when the project's own validation recorded that it is not.
    errata = mep_errata.mei_errata_field(c["pack_hash"]) or {}
    n_missing = len(errata.get("known_missing") or [])
    if not entry_mod.mei_entry_preconditions_ok(c["pack_url"], c["pack_hash"], system):
        _warn(f"issue #{issue}: missing/invalid Pack URL/Hash, or no MEI system ({system!r}); omitting JSON entry.")
        return markdown.build_row(issue, status, details, form, n_missing), None
    rom_sha1 = c["rom_sha1"]
    rom_crc32 = None
    target = rom_target.resolve_rom_target(form["game"])
    if not rom_sha1 and target:
        rom_sha1 = target["sha1"]
        rom_crc32 = target.get("crc32")
    entry, mismatch = build_pack_entry(issue, form["game"].strip(), system, form["license"],
        c["pack_url"], c["pack_hash"], rom_sha1, status, c["mep_meta"], votes=c["votes"],
        crc32=rom_crc32)
    if entry and target:
        primary = (entry.get("rom") or {}).get("sha1")
        extras = [s for s in target.get("alt_sha1") or [] if s and s != primary]
        if extras:
            # MEI v1.2 §2.4: additive exact-match alternates (No-Intro revisions/
            # alt dumps of the resolved title), never repeating rom.sha1.
            # The document declares MEI 1.4.0 (mei_catalog_entry.MEI_VERSION).
            entry.setdefault("rom", {})["sha1s"] = extras
    if mismatch:
        _warn(f"issue #{issue}: mep-meta source_sha256 disagrees with Pack Hash; omitting deps/recipe.")
    if not mei_entry_conforms(entry, entry.get("kind")):
        _warn(f"issue #{issue}: kind 'mep' but no mep-meta pack.version/mep; omitting its JSON entry.")
        return markdown.build_row(issue, status, details, form, n_missing), None
    return markdown.build_row(issue, status, details, form, n_missing), entry


def main():
    candidates = [c for c in (_candidate(item) for item in fetch_accepted_items(ACCEPTED_STATUSES)) if c]
    kept, reasons = pack_id_rules.select_catalog_rows(candidates)
    for issue, (reason, anchor) in sorted(reasons.items()):
        note = {"duplicate": f"same content_id as #{anchor} — byte-duplicate, not listed twice",
                "origin": f"claims an existing pack_id from a different origin (bound to '{anchor}') — not listed",
                }.get(reason, f"revision of its pack_id loses the slot to #{anchor} — not listed")
        _warn(f"issue #{issue}: {note} (PRD §3.3/§3.6).")
    rows, entries = [], []
    for c in kept:
        row, entry = _render(c)
        #ADR-0154 §3: the disclosure rides on the row rather than through
        #`build_row`, whose renderer this slice does not own; see
        #`with_generated_column`.
        row["generated"] = c.get("generated")
        rows.append(row)
        if entry is not None:
            entries.append(entry)
    OUTPUT_PATH.write_text(
        disclosure.with_generated_column(markdown.build_markdown(rows), rows,
                                         markdown.TABLE_HEADER, markdown.TABLE_SEP,
                                         markdown.POPULARITY_NOTE),
        encoding="utf-8")
    catalog = entry_mod.build_catalog(entries, date.today().isoformat())
    JSON_OUTPUT_PATH.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"docs/community-packs.md regenerated with {len(rows)} accepted pack(s); "
          f"docs/community-packs.json with {len(catalog['packs'])} MEI pack entry(ies).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
