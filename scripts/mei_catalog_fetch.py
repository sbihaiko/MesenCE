#!/usr/bin/env python3
"""mei_catalog_fetch — the gh-backed read half of the community-pack catalog
generator (ADR-0138 §35 split: the generator orchestrates, this module
fetches, `mei_catalog_entry` assembles, `community_pack_markdown` renders).

Holds every live `gh` call the generator makes (board item-list, per-issue
view, mep-meta comments) plus the Issue Form field extraction — so the
generator stays a pure-ish orchestrator over fetched data. `fetch_accepted_
items` documents the CONFIRMED-vs-COVERAGE-GAP facts (which `gh project`
field ids were verified live against the real API vs. which per-item JSON
key names remain an unconfirmed gap because the Project held zero items at
write time); the item accessors use defensive `dict.get` lookups, never
direct indexing on an assumed key path.

stdlib only (plus the stdlib-only leaves `mep_meta_parser`,
`community_pack_markdown`, `mei_catalog_entry`).
"""
from __future__ import annotations

import json
import re
import subprocess

import community_pack_markdown as markdown
from mep_meta_parser import MARKER as MEP_META_MARKER, parse_mep_meta

REPO = "sbihaiko/MesenCE"
OWNER = "sbihaiko"
PROJECT_NUMBER = 3


def run_gh(args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return result.stdout


def fetch_accepted_items(accepted_statuses):
    """Lists the Project 3 items whose Status is one of the accepted states.

    CONFIRMED live (gh 2.83.1) against the real GitHub API: the Status field
    id (PVTSSF_lAHOB1MsbM4BhjpNzhge86c) and the Pack Hash one
    (PVTF_lAHOB1MsbM4BhjpNzhge9Is), via `gh project field-list`. Per-item key
    names were an open COVERAGE GAP at write time (`gh project item-list`
    returned zero items) and are now CONFIRMED (2026-08-29, board holds 11
    accepted items): `gh project item-list` lowercases the first letter of
    each Project field name, so "Pack URL"/"Pack Hash"/"ROM SHA1" surface as
    "pack URL"/"pack Hash"/"ROM SHA1" item keys. The accessors below check the
    confirmed lowercase key first and keep camelCase/underscore aliases for
    safety; parsing never crashes on an unexpected key.
    """
    raw = run_gh(["project", "item-list", str(PROJECT_NUMBER), "--owner", OWNER, "--format", "json"])
    items = json.loads(raw).get("items", [])
    return [it for it in items if item_status(it) in accepted_statuses]


def item_status(item):
    return item.get("status") or item.get("Status") or ""


def item_issue_number(item):
    content = item.get("content") or {}
    return content.get("number") or item.get("number") or item.get("issue_number")


def item_pack_url(item):
    # `gh project item-list` lowercases the first letter of each Project field
    # name when building its JSON keys: the "Pack URL" field surfaces as
    # "pack URL" (CONFIRMED 2026-08-29 against the live board, which the
    # COVERAGE-GAP note below could not do at write time). Check the lowercase
    # key first, keep the camelCase/underscore aliases for safety.
    return (item.get("pack URL") or item.get("Pack URL")
            or item.get("packUrl") or item.get("pack_url"))


def item_pack_hash(item):
    return (item.get("pack Hash") or item.get("Pack Hash")
            or item.get("packHash") or item.get("pack_hash"))


def item_rom_sha1(item):
    # The ROM SHA1 field is returned by item-list only when populated; the
    # generator treats it as optional (None -> MEI entry without a rom_sha1).
    return (item.get("ROM SHA1") or item.get("romSha1")
            or item.get("rom_sha1"))


def fetch_issue_details(issue_number):
    raw = run_gh(["issue", "view", str(issue_number), "--repo", REPO,
                  "--json", "author,createdAt,title,labels,url,reactionGroups,body"])
    return json.loads(raw)


def fetch_mep_meta_comment_body(issue_number):
    raw = run_gh(["api", f"repos/{REPO}/issues/{issue_number}/comments", "--paginate"])
    try:
        comments = json.loads(raw)
    except json.JSONDecodeError:
        comments = None
    comments = comments if isinstance(comments, list) else []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        login = (comment.get("user") or {}).get("login")
        body = comment.get("body") or ""
        if login == OWNER and MEP_META_MARKER in body:
            return body
    return None


def fetch_mep_meta(issue_number):
    """Parses this issue's bot-owned mep-meta comment, or None if absent."""
    body = fetch_mep_meta_comment_body(issue_number)
    return parse_mep_meta(body) if body else None


def parse_form_field(body, heading):
    """The answer under a '### <heading>' Issue Form section; None when absent."""
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
