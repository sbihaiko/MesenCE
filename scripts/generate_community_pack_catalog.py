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
(ADR-0138 §26-27), deriving `kind` from the board Status and `deps[]`/
`recipe` from the issue's `<!-- mep-meta -->` block via `mep_meta_parser`.

stdlib only. Usage: python3 scripts/generate_community_pack_catalog.py
"""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from mep_meta_parser import MARKER as MEP_META_MARKER, parse_mep_meta

REPO = "sbihaiko/MesenCE"
OWNER = "sbihaiko"
PROJECT_NUMBER = 3

ACCEPTED_STATUSES = {"Aceito parcial (HD Mesen)", "Aceito (MEP completo)"}
CONSOLE_LABELS = {"nes", "snes", "gb", "gbc", "sms", "other"}

# Mirrors validate-specs.py's SYSTEMS/SHA256_HEX exactly (validate_mei's own
# constraints on `system`/`sha256`) — kept as separate literals rather than
# an import so this stdlib-only generator never depends on a CLI-shaped
# sibling script. `system` is deliberately narrower than CONSOLE_LABELS
# above: the Issue Form's "Other" option (.github/ISSUE_TEMPLATE/
# community-pack.yml) has no MEI-representable system, so it belongs in the
# tolerant Markdown table but not in a validate_mei-conformant JSON entry.
MEI_SYSTEMS = {"nes", "gb", "gbc", "sms", "gg", "sg1000", "coleco", "snes"}
SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "community-packs.md"
JSON_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "community-packs.json"
TABLE_HEADER = "| Link | Game | Console | Author | Category | Date | External assets |"
TABLE_SEP = "|---|---|---|---|---|---|---|"

MEI_VERSION = "1.1.0"
CATALOG_NAME = "MesenCE community packs"
MAINTAINER = "sbihaiko"

# Board Status literals stay exactly as configured on the GitHub Project
# (Portuguese literals per CLAUDE.md) — never translated here.
STATUS_MEP_COMPLETO = "Aceito (MEP completo)"
STATUS_HD_PARCIAL = "Aceito parcial (HD Mesen)"


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
    (item_pack_url/item_pack_hash/item_rom_sha1 below) share this same gap, so all of them use
    defensive, non-crashing `dict.get` lookups instead of direct indexing.
    """
    raw = run_gh(["project", "item-list", str(PROJECT_NUMBER), "--owner", OWNER, "--format", "json"])
    items = json.loads(raw).get("items", [])
    return [it for it in items if item_status(it) in ACCEPTED_STATUSES]


def item_status(item):
    """Defensive lookup of the item's Status (same coverage gap as above)."""
    return item.get("status") or item.get("Status") or ""


def item_issue_number(item):
    """Defensive lookup of the source issue number, trying the plausible formats."""
    content = item.get("content") or {}
    return content.get("number") or item.get("number") or item.get("issue_number")


def item_pack_url(item):
    """Defensive lookup of the item's Pack URL field (same coverage gap as above)."""
    return item.get("packUrl") or item.get("Pack URL") or item.get("pack_url")


def item_pack_hash(item):
    """Defensive lookup of the item's Pack Hash field (same coverage gap as above)."""
    return item.get("packHash") or item.get("Pack Hash") or item.get("pack_hash")


def item_rom_sha1(item):
    """Defensive lookup of the item's ROM SHA1 field (same coverage gap as above)."""
    return item.get("romSha1") or item.get("ROM SHA1") or item.get("rom_sha1")


def kind_from_status(status):
    """Derives MEI `kind` from the board Status literal (ADR-0138 §3/§26).

    No automated verdict path currently produces STATUS_MEP_COMPLETO (only
    a human moving the board item can), so today's catalog is expected to
    be all "hd-legacy" — this still implements the "mep" branch for when
    that changes. Returns None for any other Status (defensive default:
    the caller then omits `kind` entirely rather than guess).
    """
    if status == STATUS_MEP_COMPLETO:
        return "mep"
    if status == STATUS_HD_PARCIAL:
        return "hd-legacy"
    return None


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
    if status == STATUS_MEP_COMPLETO:
        return "Full MEP"
    if status == STATUS_HD_PARCIAL:
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


def _dep_entry(dep):
    """Maps one `recipe.sources.deps[]` item to its MEI `deps[]` shape."""
    entry = {"id": dep.get("id"), "license": dep.get("license") or "unknown"}
    if dep.get("sha256"):
        entry["sha256"] = dep["sha256"]
    if dep.get("size") is not None:
        entry["size"] = dep["size"]
    hints = dep.get("hints") or []
    if hints:
        entry["url"] = hints[0]
    return entry


def dep_entries_from_recipe(mep_meta):
    """Extracts MEI `deps[]` from mep-meta's embedded `recipe.sources.deps`.

    Deliberately NOT mep-meta's own top-level stripped `deps` field (just
    `id`/`sha256`/`size` — see the "Upsert mep-meta comment" step): that
    field lacks `license`, which MEI-v1 §2.3 and MEP-recipe-v1 §3.3 both
    require/carry per dep. Returns None (not `[]`) when there is nothing to
    report, so the caller can omit the key rather than emit an empty list.
    """
    if not isinstance(mep_meta, dict):
        return None
    recipe = mep_meta.get("recipe")
    if not isinstance(recipe, dict):
        return None
    deps = (recipe.get("sources") or {}).get("deps") or []
    if not deps:
        return None
    return [_dep_entry(dep) for dep in deps]


def recipe_fields(mep_meta, pack_hash):
    """Returns (deps, recipe, recipe_hash, recipe_ok, mismatch).

    ADR-0138 §18 "two stores, one rule": when mep-meta's `source_sha256`
    disagrees with the Project "Pack Hash" field, the field wins — deps and
    the recipe document are omitted for this entry and `mismatch` is True
    so the caller can log it (never a fatal error for the whole run).
    """
    if not isinstance(mep_meta, dict):
        return None, None, None, None, False
    source_sha256 = mep_meta.get("source_sha256")
    if pack_hash and source_sha256 and source_sha256 != pack_hash:
        return None, None, None, None, True
    deps = dep_entries_from_recipe(mep_meta)
    recipe = mep_meta.get("recipe")
    recipe = recipe if isinstance(recipe, dict) else None
    recipe_hash = mep_meta.get("recipe_hash") if recipe else None
    recipe_ok = mep_meta.get("recipe_ok") if recipe else None
    return deps, recipe, recipe_hash, recipe_ok, False


def _entry_base(issue_number, game, system, license_, pack_url, pack_hash, rom_sha1, kind):
    """Builds the fields every entry has regardless of `kind` or mep-meta."""
    rom = {"sha1": rom_sha1} if rom_sha1 else {}
    name = f"{game} — community submission" if kind == "hd-legacy" else game
    entry = {
        "issue": issue_number,
        "name": name,
        "game": game,
        "system": system,
        "rom": rom,
        "license": license_ or "unknown",
        "url": pack_url or "",
        "sha256": pack_hash or "",
    }
    if kind:
        entry["kind"] = kind
    return entry


def _apply_mep_meta_passthrough(entry, mep_meta):
    """Copies verdict/validated_at/labels from mep-meta verbatim (§26)."""
    if not isinstance(mep_meta, dict):
        return
    for key in ("verdict", "validated_at", "labels"):
        if mep_meta.get(key):
            entry[key] = mep_meta[key]


def build_pack_entry(issue_number, game, system, license_, pack_url, pack_hash, rom_sha1, status, mep_meta):
    """Assembles one MEI v1.1 packs[] entry (ADR-0138 §26/§27).

    Returns (entry, mismatch) — see recipe_fields for `mismatch`.
    """
    kind = kind_from_status(status)
    entry = _entry_base(issue_number, game, system, license_, pack_url, pack_hash, rom_sha1, kind)
    deps, recipe, recipe_hash, recipe_ok, mismatch = recipe_fields(mep_meta, pack_hash)
    if deps:
        entry["deps"] = deps
    if recipe:
        entry["recipe"] = recipe
    if recipe_hash:
        entry["recipe_hash"] = recipe_hash
    if recipe_ok is not None:
        entry["recipe_ok"] = recipe_ok
    _apply_mep_meta_passthrough(entry, mep_meta)
    return entry, mismatch


def mei_entry_preconditions_ok(pack_url, pack_hash, system):
    """Whether this item has everything validate_mei (scripts/validate-specs.py)
    requires of a `packs[]` entry's `url`/`sha256`/`system` (MEI-v1 §2).

    Returns False when the Project's Pack URL/Pack Hash fields are absent
    or malformed (the item_pack_url/item_pack_hash coverage gap documented
    on fetch_accepted_items above), or when the Issue Form's Console value
    has no MEI-representable system — the Form offers a first-class
    "Other" option (.github/ISSUE_TEMPLATE/community-pack.yml) that
    lowercases to "other", and a missing/unmapped console falls back to
    "?" (console_from_labels) — neither of which is in MEI_SYSTEMS. The
    caller then omits the JSON entry entirely rather than emit one
    validate_mei would reject; the Markdown row still renders for that
    item, tolerant of "?"/"other" (AC-6's six pre-existing columns).
    """
    return (
        bool(pack_url) and pack_url.startswith("https://")
        and bool(pack_hash) and bool(SHA256_HEX.match(pack_hash))
        and system in MEI_SYSTEMS
    )


def build_catalog(entries, updated):
    """Wraps entries into the top-level MEI v1.1 catalog document (§26)."""
    return {
        "mei": MEI_VERSION,
        "name": CATALOG_NAME,
        "maintainer": MAINTAINER,
        "updated": updated,
        "packs": entries,
    }


def build_row(item, details, form, has_deps=False):
    """Builds a Markdown catalog row combining the Project item and the issue."""
    issue_number = item_issue_number(item)
    status = item_status(item)
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


def _fetch_mep_meta(issue_number):
    """Fetches this issue's bot-owned mep-meta comment and parses it, or
    None when there is no such comment or it fails to parse."""
    body = fetch_mep_meta_comment_body(issue_number)
    return parse_mep_meta(body) if body else None


def _warn_missing_mei_preconditions(issue_number, system):
    print(f"WARNING: issue #{issue_number} is missing/invalid Pack URL, Pack Hash, "
          f"or has no MEI-representable system ({system!r}); omitting its "
          f"docs/community-packs.json entry (Markdown row still included).",
          file=sys.stderr)


def _warn_source_sha256_mismatch(issue_number):
    print(f"WARNING: mep-meta source_sha256 disagrees with the Project Pack Hash "
          f"field for issue #{issue_number}; omitting deps/recipe (field wins).",
          file=sys.stderr)


def _build_entry_for_accepted_item(item):
    """Fetches issue + mep-meta data for one accepted item and returns
    (markdown_row, mei_entry_or_None). mei_entry is None both for an item
    with no linked issue and for one missing an MEI-conformant Pack URL/
    Pack Hash/system (mei_entry_preconditions_ok) — the Markdown row is
    still produced in both cases."""
    issue_number = item_issue_number(item)
    if issue_number is None:
        return build_row(item, {}, {"game": "", "console": "", "license": "unknown"}), None
    details = fetch_issue_details(issue_number)
    form = issue_form_fields(details)
    pack_url, pack_hash = item_pack_url(item), item_pack_hash(item)
    system = (form["console"] or "?").strip().lower()
    if not mei_entry_preconditions_ok(pack_url, pack_hash, system):
        _warn_missing_mei_preconditions(issue_number, system)
        return build_row(item, details, form, has_deps=False), None
    entry, mismatch = build_pack_entry(
        issue_number=issue_number, game=form["game"].strip(), system=system,
        license_=form["license"], pack_url=pack_url, pack_hash=pack_hash,
        rom_sha1=item_rom_sha1(item), status=item_status(item),
        mep_meta=_fetch_mep_meta(issue_number),
    )
    if mismatch:
        _warn_source_sha256_mismatch(issue_number)
    return build_row(item, details, form, has_deps=bool(entry.get("deps"))), entry


def main():
    items = fetch_accepted_items()
    rows, entries = [], []
    for item in items:
        row, entry = _build_entry_for_accepted_item(item)
        rows.append(row)
        if entry is not None:
            entries.append(entry)
    OUTPUT_PATH.write_text(build_markdown(rows), encoding="utf-8")
    catalog = build_catalog(entries, date.today().isoformat())
    JSON_OUTPUT_PATH.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"docs/community-packs.md regenerated with {len(rows)} accepted pack(s).")
    print(f"docs/community-packs.json regenerated with {len(entries)} MEI pack entry(ies).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
