#!/usr/bin/env python3
"""generate_community_pack_catalog.py — regenerates docs/community-packs.md.

Reads the accepted items from the "MesenCE Community Packs" board (Project
3, owner sbihaiko, node id PVT_kwHOB1MsbM4BhjpN) via `gh project item-list`
and, for each source issue, fetches author/date/console/reactions via
`gh issue view`. Rewrites docs/community-packs.md with a
link/game/console/author/category/date table and a "Most popular" section
ranked by 👍 reactions — a popularity proxy, not a real usage metric (no
telemetry is implemented here or anywhere else in this repository).

stdlib only (subprocess + json), in the style of scripts/report-bug.sh and
scripts/mep_lint.py.

Usage: python3 scripts/generate_community_pack_catalog.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = "sbihaiko/MesenCE"
OWNER = "sbihaiko"
PROJECT_NUMBER = 3

ACCEPTED_STATUSES = {"Aceito parcial (HD Mesen)", "Aceito (MEP completo)"}
CONSOLE_LABELS = {"nes", "snes", "gb", "gbc", "sms", "other"}
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "community-packs.md"
TABLE_HEADER = "| Link | Game | Console | Author | Category | Date |"
TABLE_SEP = "|---|---|---|---|---|---|"


def run_gh(args):
    """Runs `gh` and returns stdout; stderr/error propagate to the job log."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return result.stdout


def fetch_accepted_items():
    """Lists the Project 3 items whose Status is one of the two "Aceito*"
    states.

    Provenance note (confirmed live in this session, gh 2.83.1):
    `gh project field-list 3 --owner sbihaiko --format json` CONFIRMS the
    Status field id (PVTSSF_lAHOB1MsbM4BhjpNzhge86c, with the task's 5
    options) and the Pack Hash one (PVTF_lAHOB1MsbM4BhjpNzhge9Is) against
    the real GitHub API. The per-item key names from `gh project item-list 3
    --owner sbihaiko --format json`, however, remain an open, audited
    COVERAGE GAP: that same call, in a real session, returned
    `{"items":[],"totalCount":0}` — the Project has zero items at the time
    this script was written, so there is no populated example to confirm
    those key names against real data. The gap is in the live datastore
    itself (no populated item exists yet), not just in a cached view, and is
    not presented here as settled fact — any negative/absent-key conclusion
    below is qualified by this gap. `extract_row` uses defensive,
    non-crashing lookups (`dict.get`) instead of direct indexing, so that a
    real schema different from the expected one fails visibly (a row with
    placeholders) instead of taking down the script or silently filing the
    wrong item.
    """
    raw = run_gh(["project", "item-list", str(PROJECT_NUMBER), "--owner", OWNER, "--format", "json"])
    items = json.loads(raw).get("items", [])
    return [it for it in items if _item_status(it) in ACCEPTED_STATUSES]


def _item_status(item):
    """Defensive lookup of the item's Status (see the provenance note in fetch_accepted_items)."""
    return item.get("status") or item.get("Status") or ""


def _item_issue_number(item):
    """Defensive lookup of the source issue number, trying the plausible formats."""
    content = item.get("content") or {}
    return content.get("number") or item.get("number") or item.get("issue_number")


def fetch_issue_details(issue_number):
    """Fetches the issue's author/date/labels/reactions via `gh issue view`.

    Field confirmed live in this session: the correct JSON field name is
    `reactionGroups` (not `reactions` — `gh issue view --json reactions`
    fails with "Unknown JSON field" on gh 2.83.1). Populated format
    confirmed live (a test reaction added and removed via `gh api graphql`
    addReaction/removeReaction in this session):
    `[{"content": "THUMBS_UP", "users": {"totalCount": N}}, ...]`, only with
    count groups > 0; an empty list when there are no reactions.
    """
    raw = run_gh(["issue", "view", str(issue_number), "--repo", REPO,
                  "--json", "author,createdAt,title,labels,url,reactionGroups,body"])
    return json.loads(raw)


def _parse_form_field(body, heading):
    """Extracts the answer under a '### <heading>' section of an Issue Form body.

    Issue Forms always render a submitted field as a Markdown '### <label>'
    heading followed by the answer, up to the next '### ' heading or the end
    of the body (confirmed live against issues #6/#7/#8's rendered bodies —
    see .github/ISSUE_TEMPLATE/community-pack.yml for the field labels).
    Returns None (not "?") when the heading isn't found or the answer is
    empty, so callers can fall back to another source instead of an empty
    string leaking into the catalog.
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


def _escape_table_cell(value):
    """Collapses whitespace/newlines and escapes '|' for a Markdown table cell.

    Needed once free-form issue-body text (not just labels/title) starts
    flowing into the table — a submitter's answer could otherwise contain a
    literal '|' or a line break and break the table's row structure.
    """
    return re.sub(r"\s+", " ", str(value)).replace("|", "\\|").strip()


def _thumbs_up_count(details):
    """Defensive sum of THUMBS_UP reactions from reactionGroups."""
    for group in details.get("reactionGroups") or []:
        if group.get("content") == "THUMBS_UP":
            users = group.get("users") or {}
            return users.get("totalCount", 0)
    return 0


def _console_from_labels(labels):
    for label in labels or []:
        name = (label.get("name") or "").strip().lower()
        if name in CONSOLE_LABELS:
            return name
    return "?"


def _categoria_from_status(status):
    if status == "Aceito (MEP completo)":
        return "Full MEP"
    if status == "Aceito parcial (HD Mesen)":
        return "Partial HD"
    return status or "?"


def build_row(item):
    """Builds a catalog row combining the Project item and the issue."""
    issue_number = _item_issue_number(item)
    status = _item_status(item)
    if issue_number is None:
        return {"jogo": "(no issue)", "console": "?", "autor": "?",
                "categoria": _categoria_from_status(status), "data": "?", "url": "", "thumbs_up": 0}
    details = fetch_issue_details(issue_number)
    author = (details.get("author") or {}).get("login") or "?"
    body = details.get("body") or ""
    # Prefer the Issue Form's own structured fields over the issue title/
    # labels — title is free text (often just restating the pack name, not
    # the target ROM) and no automation in this pipeline ever attaches a
    # console-name label (see the "Console" section always parsing to "?"
    # bug this fixes), so falling back to them only covers issues that
    # don't follow the current form shape (e.g. hand-created ones).
    game = _parse_form_field(body, "Target game/ROM and region") or details.get("title") or "(no title)"
    console = _parse_form_field(body, "Console") or _console_from_labels(details.get("labels"))
    return {
        "jogo": _escape_table_cell(game),
        "console": _escape_table_cell(console),
        "autor": _escape_table_cell(author),
        "categoria": _categoria_from_status(status),
        "data": (details.get("createdAt") or "?")[:10],
        "url": details.get("url") or "",
        "thumbs_up": _thumbs_up_count(details),
    }


def render_table(rows):
    lines = [TABLE_HEADER, TABLE_SEP]
    if not rows:
        lines.append("| _no packs accepted yet_ | | | | | |")
    for row in rows:
        link = f"[link]({row['url']})" if row["url"] else "-"
        lines.append(f"| {link} | {row['jogo']} | {row['console']} | {row['autor']} | {row['categoria']} | {row['data']} |")
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


def main():
    items = fetch_accepted_items()
    rows = [build_row(item) for item in items]
    OUTPUT_PATH.write_text(build_markdown(rows), encoding="utf-8")
    print(f"docs/community-packs.md regenerated with {len(rows)} accepted pack(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
