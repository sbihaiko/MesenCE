#!/usr/bin/env python3
"""community_pack_row — dependency-free leaf module holding the pure Issue
Form/Markdown-row logic shared by generate_community_pack_catalog.py's two
writers (the Markdown table and the MEI JSON catalog, F6.3). No `gh`/
network I/O of its own — operates only on an already-fetched issue
`details` dict (see generate_community_pack_catalog.py's fetch_issue_details).
Split out per scripts/AGENTS.md's split convention (ADR-0138 Clarification
§24) purely to keep the generator's own file under this repo's per-file
line budget.

stdlib only.
"""
import re

CONSOLE_LABELS = {"nes", "snes", "gb", "gbc", "sms", "other"}

def parse_form_field(body, heading):
    """Extracts the answer under a '### <heading>' section of an Issue Form body.

    Issue Forms always render a submitted field as a Markdown '### <label>'
    heading followed by the answer, up to the next '### ' heading or the end
    of the body (confirmed live against issues #6/#7/#8's rendered bodies —
    see .github/ISSUE_TEMPLATE/community-pack.yml for the field labels).
    Returns None (not "?") when the heading isn't found or the answer is
    empty, so callers can fall back to another source.
    """
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

def escape_table_cell(value):
    """Collapses whitespace/newlines and escapes '|' for a Markdown table cell."""
    return re.sub(r"\s+", " ", str(value)).replace("|", "\\|").strip()

def thumbs_up_count(details):
    """Defensive sum of THUMBS_UP reactions from reactionGroups."""
    for group in details.get("reactionGroups") or []:
        if group.get("content") == "THUMBS_UP":
            users = group.get("users") or {}
            return users.get("totalCount", 0)
    return 0

def console_from_labels(labels):
    for label in labels or []:
        name = (label.get("name") or "").strip().lower()
        if name in CONSOLE_LABELS:
            return name
    return "?"

def category_from_status(status):
    if status == "Aceito (MEP completo)":
        return "Full MEP"
    if status == "Aceito parcial (HD Mesen)":
        return "Partial HD"
    return status or "?"

def issue_form_fields(details):
    """Parses the Issue Form fields shared by the Markdown row and the MEI
    entry, so game/console/license never drift between the two outputs.

    Prefers the Issue Form's own structured fields over the issue title/
    labels — title is free text and no automation attaches a console-name
    label — falling back to them only covers issues that predate the
    current form shape (e.g. hand-created ones).
    """
    body = details.get("body") or ""
    game = parse_form_field(body, "Target game/ROM and region") or details.get("title") or "(no title)"
    console = parse_form_field(body, "Console") or console_from_labels(details.get("labels"))
    license_ = parse_form_field(body, "External assets license (optional)") or "unknown"
    return {"game": game, "console": console, "license": license_}
