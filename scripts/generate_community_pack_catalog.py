#!/usr/bin/env python3
"""generate_community_pack_catalog.py — regenerates docs/community-packs.md
and docs/community-packs.json.

Fetches accepted items from the "MesenCE Community Packs" board (Project 3,
owner sbihaiko) via `gh project item-list`, then per issue via `gh issue view`
plus the bot-owned `<!-- mep-meta -->` comment (`mep_meta_parser.parse_mep_
meta`, ADR-0138 §27), whose `author` is the catalog's Author column (the
classify step reads it off the pack; the Issue Form no longer asks, and the
old form field is only a fallback for issues that predate the change).
Delegates MEI entry assembly (kind "mep"/"hd-legacy" derivation/validation,
§26/§28) to `mei_catalog_entry` and Markdown rendering (the Game/Console/
Author/Date/👍 table, whose 👍 cell links to the submission issue; rows ordered
via `sorted(rows, key=lambda r: r['thumbs_up'], reverse=True)` on
community 👍 votes, no usage telemetry) to `community_pack_markdown`,
then writes docs/community-packs.md and docs/community-packs.json
(JSON_OUTPUT_PATH) via json.dumps()/.write_text(). Re-exports `build_pack_
entry`/`mei_entry_conforms`/`normalized_rom_sha1`/`STATUS_MEP_COMPLETO`/
`STATUS_HD_PARCIAL` as a back-compat facade (ADR-0138 §24).

stdlib only. Usage: python3 scripts/generate_community_pack_catalog.py
"""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import community_pack_markdown as markdown
import mei_catalog_entry as entry_mod
from mei_catalog_entry import (  # noqa: F401 -- facade re-export (ADR-0138 §24)
    STATUS_HD_PARCIAL,
    STATUS_MEP_COMPLETO,
    build_pack_entry,
    mei_entry_conforms,
    normalized_rom_sha1,
)
from mep_meta_parser import MARKER as MEP_META_MARKER, parse_mep_meta

REPO = "sbihaiko/MesenCE"
OWNER = "sbihaiko"
PROJECT_NUMBER = 3

ACCEPTED_STATUSES = {STATUS_HD_PARCIAL, STATUS_MEP_COMPLETO}
CONSOLE_LABELS = markdown.CONSOLE_LABELS
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "community-packs.md"
JSON_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "community-packs.json"


def run_gh(args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return result.stdout


def fetch_accepted_items():
    """Lists the Project 3 items whose Status is one of the two "Aceito*" states.

    CONFIRMED live (gh 2.83.1) against the real GitHub API: the Status field id
    (PVTSSF_lAHOB1MsbM4BhjpNzhge86c) and the Pack Hash one (PVTF_lAHOB1MsbM4BhjpNzhge9Is).
    Per-item key names remain an open COVERAGE GAP -- `gh project item-list` returned zero
    items at write time -- so this and the Pack URL/Hash/ROM SHA1 reads below all use
    defensive `dict.get` lookups instead of direct indexing.
    """
    raw = run_gh(["project", "item-list", str(PROJECT_NUMBER), "--owner", OWNER, "--format", "json"])
    items = json.loads(raw).get("items", [])
    return [it for it in items if item_status(it) in ACCEPTED_STATUSES]


def item_status(item):
    return item.get("status") or item.get("Status") or ""


def item_issue_number(item):
    content = item.get("content") or {}
    return content.get("number") or item.get("number") or item.get("issue_number")


def item_pack_url(item):
    return item.get("packUrl") or item.get("Pack URL") or item.get("pack_url")


def item_pack_hash(item):
    return item.get("packHash") or item.get("Pack Hash") or item.get("pack_hash")


def item_rom_sha1(item):
    return item.get("romSha1") or item.get("ROM SHA1") or item.get("rom_sha1")


def fetch_issue_details(issue_number):
    raw = run_gh(["issue", "view", str(issue_number), "--repo", REPO,
                  "--json", "author,createdAt,title,labels,url,reactionGroups,body"])
    return json.loads(raw)


def fetch_mep_meta_comment_body(issue_number):
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


def parse_form_field(body, heading):
    """Extracts the answer under a '### <heading>' Issue Form section; None when absent/empty."""
    if not body:
        return None
    pattern = re.compile(
        r"^###\s+" + re.escape(heading) + r"\s*\n+(.*?)(?=\n###\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def issue_form_fields(details):
    """Form fields the row/MEI entry share ("credits" = declared pack author)."""
    body = details.get("body") or ""
    game = parse_form_field(body, "Target game/ROM and region") or details.get("title") or "(no title)"
    console = parse_form_field(body, "Console") or markdown.console_from_labels(details.get("labels"))
    license_ = parse_form_field(body, "External assets license (optional)") or "unknown"
    credits = parse_form_field(body, "Author/credits")
    return {"game": game, "console": console, "license": license_, "credits": credits}


def _fetch_mep_meta(issue_number):
    """Parses this issue's bot-owned mep-meta comment, or None if absent/unparseable."""
    body = fetch_mep_meta_comment_body(issue_number)
    return parse_mep_meta(body) if body else None


def _warn(message):  # non-fatal per-item warning; never aborts the whole run
    print(f"WARNING: {message}", file=sys.stderr)


def _build_entry_for_accepted_item(item):
    """Returns (markdown_row, mei_entry_or_None): mei_entry is None for a
    missing issue, non-conformant Pack URL/Hash/system, or a
    `mei_entry_conforms` failure -- the row still renders regardless."""
    issue_number = item_issue_number(item)
    status = item_status(item)
    if issue_number is None:
        empty_form = {"game": "", "console": "", "license": "unknown", "credits": None}
        return markdown.build_row(None, status, {}, empty_form), None
    details = fetch_issue_details(issue_number)
    form = issue_form_fields(details)
    mep_meta = _fetch_mep_meta(issue_number)
    # Authorship comes from the pack itself (classify writes it into mep-meta);
    # the form field is only a fallback for issues that predate that change.
    form["credits"] = (mep_meta or {}).get("author") or form["credits"]
    pack_url, pack_hash = item_pack_url(item), item_pack_hash(item)
    system = (form["console"] or "?").strip().lower()
    if not entry_mod.mei_entry_preconditions_ok(pack_url, pack_hash, system):
        _warn(f"issue #{issue_number}: missing/invalid Pack URL/Hash, or no MEI system ({system!r}); omitting JSON entry.")
        return markdown.build_row(issue_number, status, details, form), None
    entry, mismatch = build_pack_entry(
        issue_number=issue_number, game=form["game"].strip(), system=system,
        license_=form["license"], pack_url=pack_url, pack_hash=pack_hash,
        rom_sha1=item_rom_sha1(item), status=status, mep_meta=mep_meta,
    )
    if mismatch:
        _warn(f"issue #{issue_number}: mep-meta source_sha256 disagrees with Pack Hash; omitting deps/recipe.")
    if not mei_entry_conforms(entry, entry.get("kind")):
        _warn(f"issue #{issue_number}: kind 'mep' but no mep-meta pack.version/mep; omitting its JSON entry.")
        return markdown.build_row(issue_number, status, details, form), None
    return markdown.build_row(issue_number, status, details, form), entry


def main():
    items = fetch_accepted_items()
    rows, entries = [], []
    for item in items:
        row, entry = _build_entry_for_accepted_item(item)
        rows.append(row)
        if entry is not None:
            entries.append(entry)
    OUTPUT_PATH.write_text(markdown.build_markdown(rows), encoding="utf-8")
    catalog = entry_mod.build_catalog(entries, date.today().isoformat())
    JSON_OUTPUT_PATH.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"docs/community-packs.md regenerated with {len(rows)} accepted pack(s).")
    print(f"docs/community-packs.json regenerated with {len(catalog['packs'])} MEI pack entry(ies).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
