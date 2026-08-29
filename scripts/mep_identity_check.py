#!/usr/bin/env python3
"""mep_identity_check — P.2 collision check for the community-pack validate
workflow (PRD-player-shell §3.3, ADR-0140/0141): after an `accepted` verdict,
tells whether the just-validated submission collides with an already-accepted
pack on the board and posts the matching notice.

Two collision kinds (each is the FIRST rule that matches; a submission can
collide at most once):

  1. `duplicate` — same `content_id` as an existing accepted item (byte-
     duplicate under another pack_id, or a wrapper-only resubmit). Not a
     second pack; comment "duplicate of #N" (PRD §3.3); still accepted, but
     the catalog generator never lists it twice.
  2. `origin` — the same `pack_id` as an existing accepted item, but from a
     DIFFERENT origin (host has no repo -> issue author's login). Not a
     revision; does not compete for the slot; the workflow adds the
     `pack:needs-review` label + a comment for human triage.

The pure decisions live in `collision()` (unit-testable without gh). The
CLI (`main`) does the live `gh` reads — board items, per-issue mep-meta
comments — and the writes (comment / label) on the runner only.

Usage (workflow):
  python3 scripts/mep_identity_check.py check \
    --issue-number N --pack-url URL --content-id HEX \
    [--classify RUNNER_TEMP/mep_classify_clean.json]
  prints the collision decision as `decision=duplicate` / `decision=origin` /
  `decision=none` plus, for duplicate, `duplicate_of=<issue>`; for origin,
  `origin=<bound>` and `holder=<issue>`. Set `--post` to also post the
  comment / label (workflow passes it; local runs use `--no-post`).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from mep_meta_parser import parse_mep_meta
import pack_id_rules

REPO = "sbihaiko/MesenCE"
OWNER = "sbihaiko"
PROJECT_NUMBER = 3
ACCEPTED_STATUSES = {"Aceito (MEP completo)", "Aceito parcial (HD Mesen)"}


def run_gh(args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return result.stdout


def _identity_of_issue(issue_number):
    """(content_id, pack_id, origin) of an already-accepted issue from its
    bot-owned mep-meta comment; all None when the comment is absent. The pack
    URL is not on the comment, so pack_id/origin are re-derived from the
    board's Pack URL field where the caller has it (see `existing_identities`)."""
    raw = run_gh(["api", f"repos/{REPO}/issues/{issue_number}/comments", "--paginate"])
    try:
        comments = json.loads(raw)
    except json.JSONDecodeError:
        return None, None, None
    for comment in comments or []:
        if (comment.get("user") or {}).get("login") == OWNER and "<!-- mep-meta -->" in (comment.get("body") or ""):
            meta = parse_mep_meta(comment.get("body") or "")
            if meta is not None:
                return meta.get("content_id"), meta.get("pack_id"), meta.get("pack_origin")
    return None, None, None


def existing_identities(board_items):
    """Pure: maps accepted board items to their {issue_number, content_id,
    pack_id, origin}. pack_id/origin come from mep-meta when the workflow
    recorded them; otherwise re-derived from the board's Pack URL (+ the
    issue's author login for hostless URLs) via pack_id_rules, so even a
    pre-P.2 item (no pack_id in mep-meta) participates in the checks."""
    identities = []
    for item in board_items:
        if item.get("status") not in ACCEPTED_STATUSES:
            continue
        issue = item.get("issue_number")
        if issue is None:
            continue
        content_id, meta_pack_id, meta_origin = _identity_of_issue(issue)
        pack_url = item.get("pack_url")
        if not meta_pack_id:
            meta_pack_id, _ = pack_id_rules.resolve_pack_id(pack_url, None, issue)
        if not meta_origin:
            # The issue author's login is the origin for hosts without a repo;
            # fetch it (a board item carries no author). Cheap: one gh call.
            details = json.loads(run_gh(["issue", "view", str(issue), "--repo", REPO,
                                         "--json", "author"]))
            meta_origin = pack_id_rules.pack_origin(pack_url, (details.get("author") or {}).get("login"))
        identities.append({
            "issue_number": issue,
            "content_id": content_id,
            "pack_id": meta_pack_id,
            "origin": meta_origin,
        })
    return identities


def collision(new_identity, existing):
    """Pure: the first collision between the new submission and an existing
    accepted pack. Returns ("duplicate", holder_issue) when `content_id` is
    present and equals an existing one; else ("origin", bound_origin,
    holder_issue) when the same pack_id is held by a different origin; else
    None. `existing` is the list from `existing_identities`."""
    content_id = new_identity.get("content_id")
    if content_id:
        for item in existing:
            if item.get("content_id") == content_id:
                return ("duplicate", item.get("issue_number"))
    pack_id = new_identity.get("pack_id")
    if pack_id:
        my_origin = new_identity.get("origin")
        for item in existing:
            if item.get("pack_id") == pack_id and item.get("origin") != my_origin:
                return ("origin", item.get("origin"), item.get("issue_number"))
    return None


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("--issue-number", required=True, type=int)
    check.add_argument("--pack-url", required=True)
    check.add_argument("--content-id", required=True)
    check.add_argument("--classify", help="path to mep_classify_clean.json (for recipe.pack.id)")
    check.add_argument("--post", action="store_true", help="post the comment/label")
    args = parser.parse_args(argv[1:])

    my_pack_id = None
    my_origin = None
    my_recipe_id = None
    if args.classify:
        try:
            classify = json.load(open(args.classify, encoding="utf-8"))
            recipe = classify.get("recipe") or {}
            pack = recipe.get("pack") or {}
            my_recipe_id = pack.get("id")
        except (OSError, ValueError):
            my_recipe_id = None
    author_details = json.loads(run_gh(["issue", "view", str(args.issue_number), "--repo", REPO,
                                        "--json", "author"]))
    issue_author = (author_details.get("author") or {}).get("login")
    my_origin = pack_id_rules.pack_origin(args.pack_url, issue_author)
    my_pack_id, _ = pack_id_rules.resolve_pack_id(args.pack_url, {"recipe": {"pack": {"id": my_recipe_id}}}, args.issue_number)

    items = []
    raw = run_gh(["project", "item-list", str(PROJECT_NUMBER), "--owner", OWNER, "--format", "json"])
    for it in json.loads(raw).get("items", []):
        content = it.get("content") or {}
        items.append({
            "status": it.get("status") or it.get("Status") or "",
            "issue_number": content.get("number") or it.get("number") or it.get("issue_number"),
            "pack_url": it.get("packUrl") or it.get("Pack URL") or it.get("pack_url"),
        })
    existing = [e for e in existing_identities(items) if e.get("issue_number") != args.issue_number]

    new_identity = {"content_id": args.content_id, "pack_id": my_pack_id, "origin": my_origin}
    decision = collision(new_identity, existing)
    if decision is None:
        print("decision=none")
        return 0
    if decision[0] == "duplicate":
        holder = decision[1]
        print(f"decision=duplicate")
        print(f"duplicate_of={holder}")
        if args.post:
            body = (
                "This submission is a byte-duplicate of [#" + str(holder) + "]("
                f"https://github.com/{REPO}/issues/{holder}) — the same resolved "
                "pack content (`content_id`, ADR-0139). It stays accepted but is "
                "not listed twice in the catalog (PRD §3.3)."
            )
            run_gh(["issue", "comment", str(args.issue_number), "--repo", REPO, "--body", body])
        return 0
    # origin collision
    bound, holder = decision[1], decision[2]
    print(f"decision=origin")
    print(f"origin={bound}")
    print(f"holder={holder}")
    if args.post:
        body = (
            "This submission claims `pack_id` **" + str(my_pack_id) + "**, which is "
            f"bound to origin **{bound}** by issue [#{holder}](https://github.com/{REPO}/issues/{holder}) "
            "(PRD §3.3 origin binding). A different origin claiming the same "
            "pack_id is not a revision: it never competes for the slot and is not "
            "listed. A maintainer may re-bind the origin (e.g. the author moved "
            "repos) or treat it as a competing pack."
        )
        run_gh(["issue", "comment", str(args.issue_number), "--repo", REPO, "--body", body])
        run_gh(["issue", "edit", str(args.issue_number), "--repo", REPO, "--add-label", "pack:needs-review"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
