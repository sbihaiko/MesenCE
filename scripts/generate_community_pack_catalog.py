#!/usr/bin/env python3
"""generate_community_pack_catalog.py — regenerates docs/community-packs.md
and docs/community-packs.json.

Reads the accepted items from the "MesenCE Community Packs" board (Project
3, owner sbihaiko, node id PVT_kwHOB1MsbM4BhjpN) via `gh project item-list`
and, for each source issue, fetches author/date/console/reactions via
`gh issue view` plus the bot-owned `<!-- mep-meta -->` comment. Rewrites
docs/community-packs.md (link/game/console/author/category/date/external-
assets table + a "Most popular" section ranked by 👍 reactions — a
popularity proxy, not a real usage metric, no telemetry exists anywhere in
this project) and writes docs/community-packs.json as an MEI v1.1 catalog
(ADR-0138 §26-27), via the dependency-free mei_catalog_entry and
community_pack_row leaf modules (scripts/AGENTS.md split convention).

stdlib only. Usage: python3 scripts/generate_community_pack_catalog.py
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import mei_catalog_entry
from community_pack_row import category_from_status, escape_table_cell, issue_form_fields, thumbs_up_count
from mep_meta_parser import MARKER as MEP_META_MARKER, parse_mep_meta

REPO = "sbihaiko/MesenCE"
OWNER = "sbihaiko"
PROJECT_NUMBER = 3

ACCEPTED_STATUSES = {"Aceito parcial (HD Mesen)", "Aceito (MEP completo)"}
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "community-packs.md"
JSON_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "community-packs.json"
TABLE_HEADER = "| Link | Game | Console | Author | Category | Date | External assets |"
TABLE_SEP = "|---|---|---|---|---|---|---|"

def run_gh(args):
    """Runs `gh` and returns stdout; stderr/error propagate to the job log."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return result.stdout

def fetch_accepted_items():
    """Lists the Project 3 items whose Status is one of the two "Aceito*" states.

    CONFIRMED live this session (gh 2.83.1): `gh project field-list 3 --owner sbihaiko
    --format json` confirms the Status field id (PVTSSF_lAHOB1MsbM4BhjpNzhge86c) and the
    Pack Hash one (PVTF_lAHOB1MsbM4BhjpNzhge9Is) against the real GitHub API. Per-item key
    names from `gh project item-list 3 --owner sbihaiko --format json` remain an open
    COVERAGE GAP: that call returned zero items at write time (`{"items":[],"totalCount":0}`)
    — a gap in the live datastore itself, not merely a cached view — so any negative/absent-key
    conclusion here is qualified by it. The new F6.3 Pack URL / ROM SHA1 reads
    (mei_catalog_entry.item_pack_url/item_pack_hash/item_rom_sha1) share this same gap, so all
    of them use defensive, non-crashing `dict.get` lookups instead of direct indexing.
    """
    raw = run_gh(["project", "item-list", str(PROJECT_NUMBER), "--owner", OWNER, "--format", "json"])
    items = json.loads(raw).get("items", [])
    return [it for it in items if mei_catalog_entry.item_status(it) in ACCEPTED_STATUSES]

def fetch_issue_details(issue_number):
    """Fetches the issue's author/date/labels/reactions via `gh issue view`.

    Field confirmed live in this session: the correct JSON field name is `reactionGroups`
    (not `reactions` — `gh issue view --json reactions` fails with "Unknown JSON field" on
    gh 2.83.1); populated format confirmed live: `[{"content": "THUMBS_UP", "users":
    {"totalCount": N}}]`, only with count groups > 0, an empty list when there are none.
    """
    raw = run_gh(["issue", "view", str(issue_number), "--repo", REPO,
                  "--json", "author,createdAt,title,labels,url,reactionGroups,body"])
    return json.loads(raw)

def fetch_mep_meta_comment_body(issue_number):
    """Fetches the bot-owned `<!-- mep-meta -->` comment body for an issue.

    Mirrors community-pack-validate.yml's own bot-owned, marker-matched, oldest-first
    comment selection (ADR-0138 §5): the earliest comment authored by OWNER whose body
    contains the marker wins. Returns None (never raises) when no such comment exists;
    the caller treats that the same as a malformed one — skip recipe data, keep the rest.
    """
    raw = run_gh(["api", f"repos/{REPO}/issues/{issue_number}/comments", "--paginate"])
    try:
        comments = json.loads(raw)
    except json.JSONDecodeError:
        comments = []
    if not isinstance(comments, list):
        comments = []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        login = (comment.get("user") or {}).get("login")
        body = comment.get("body") or ""
        if login == OWNER and MEP_META_MARKER in body:
            return body
    return None

def build_row(item, details, form, has_deps=False):
    """Builds a Markdown catalog row combining the Project item and the issue."""
    issue_number = mei_catalog_entry.item_issue_number(item)
    status = mei_catalog_entry.item_status(item)
    if issue_number is None:
        return {"jogo": "(no issue)", "console": "?", "autor": "?",
                "categoria": category_from_status(status), "data": "?", "url": "",
                "thumbs_up": 0, "external_assets": ""}
    author = (details.get("author") or {}).get("login") or "?"
    return {
        "jogo": escape_table_cell(form["game"]),
        "console": escape_table_cell(form["console"]),
        "autor": escape_table_cell(author),
        "categoria": category_from_status(status),
        "data": (details.get("createdAt") or "?")[:10],
        "url": details.get("url") or "",
        "thumbs_up": thumbs_up_count(details),
        "external_assets": "yes" if has_deps else "",
    }

def render_table(rows):
    lines = [TABLE_HEADER, TABLE_SEP]
    if not rows:
        lines.append("| _no packs accepted yet_ | | | | | | |")
    for row in rows:
        link = f"[link]({row['url']})" if row["url"] else "-"
        lines.append(
            f"| {link} | {row['jogo']} | {row['console']} | {row['autor']} | "
            f"{row['categoria']} | {row['data']} | {row['external_assets']} |"
        )
    return "\n".join(lines)

def render_popular_section(rows):
    lines = ["## Most popular", "",
             "_Ranked by 👍 reactions on the submission issue. This is a popularity proxy,_",
             "_not a real usage metric — no usage telemetry is collected by this project._", ""]
    ranked = sorted(rows, key=lambda r: r["thumbs_up"], reverse=True)
    if not ranked or ranked[0]["thumbs_up"] == 0:
        lines.append("_no packs with reactions yet._")
        return "\n".join(lines)
    for row in ranked:
        if row["thumbs_up"] <= 0:
            continue
        link = f"[{row['jogo']}]({row['url']})" if row["url"] else row["jogo"]
        lines.append(f"- {link} — 👍 {row['thumbs_up']}")
    return "\n".join(lines)

INTRO = ("Catalog generated automatically from the \"MesenCE Community\n"
         "Packs\" board (Project 3). Do not edit this file manually — it is\n"
         "overwritten by `.github/workflows/community-pack-catalog.yml`.")

def build_markdown(rows):
    return "\n\n".join([
        "# Community HD/MEP Packs",
        INTRO,
        render_table(rows),
        render_popular_section(rows),
    ]) + "\n"

def _build_entry_for_accepted_item(item):
    """Fetches issue + mep-meta data for one accepted item and returns
    (markdown_row, mei_entry_or_None). mei_entry is None for an item with
    no linked issue — there is no data to populate an MEI entry with."""
    issue_number = mei_catalog_entry.item_issue_number(item)
    if issue_number is None:
        return build_row(item, {}, {"game": "", "console": "", "license": "unknown"}), None
    details = fetch_issue_details(issue_number)
    form = issue_form_fields(details)
    mep_meta_body = fetch_mep_meta_comment_body(issue_number)
    mep_meta = parse_mep_meta(mep_meta_body) if mep_meta_body else None
    entry, mismatch = mei_catalog_entry.build_pack_entry(
        issue_number=issue_number,
        game=form["game"].strip(),
        system=(form["console"] or "?").strip().lower(),
        license_=form["license"],
        pack_url=mei_catalog_entry.item_pack_url(item),
        pack_hash=mei_catalog_entry.item_pack_hash(item),
        rom_sha1=mei_catalog_entry.item_rom_sha1(item),
        status=mei_catalog_entry.item_status(item),
        mep_meta=mep_meta,
    )
    if mismatch:
        print(f"WARNING: mep-meta source_sha256 disagrees with the Project Pack Hash "
              f"field for issue #{issue_number}; omitting deps/recipe (field wins).",
              file=sys.stderr)
    row = build_row(item, details, form, has_deps=bool(entry.get("deps")))
    return row, entry

def main():
    items = fetch_accepted_items()
    rows, entries = [], []
    for item in items:
        row, entry = _build_entry_for_accepted_item(item)
        rows.append(row)
        if entry is not None:
            entries.append(entry)
    OUTPUT_PATH.write_text(build_markdown(rows), encoding="utf-8")
    catalog = mei_catalog_entry.build_catalog(entries, date.today().isoformat())
    JSON_OUTPUT_PATH.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"docs/community-packs.md regenerated with {len(rows)} accepted pack(s).")
    print(f"docs/community-packs.json regenerated with {len(entries)} MEI pack entry(ies).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
