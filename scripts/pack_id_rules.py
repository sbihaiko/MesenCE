#!/usr/bin/env python3
"""pack_id_rules — dependency-free leaf holding the P.2 identity rules
(ADR-0140 pack_id resolution + origin binding, PRD-player-shell §3.3, and
the §3.6 one-slot winner). Consumed by the community-pack catalog generator
(`generate_community_pack_catalog.py`), the MEI entry assembler
(`mei_catalog_entry.py`) and, through the same import, the validate
workflow's mep-meta upsert — so the pack_id a submission's mep-meta records
and the pack_id the catalog resolves for it are the same function, never
two hand-copied pairings. stdlib only — no imports of any other `scripts/`
module (ADR-0138 §24 leaf convention), so every caller can depend on it
without a cycle.
"""
from __future__ import annotations

import re

# ADR-0140 pack_id source (1): the MEP `id` field must be a lowercase slug
# `[a-z0-9][a-z0-9-]{2,63}`. Anything else (uppercase, too short, spaces) is
# not a usable id and falls through to the owner/repo / issue-n sources.
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")

# Hosts whose pack URL carries a real origin (ADR-0140 source (2), §3.3):
# github.com/<owner>/<repo>/..., codeload.github.com/<owner>/<repo>/... and
# raw.githubusercontent.com/<owner>/<repo>/<branch>/... (the last is also a
# pack-download host in scripts/pack_host_allowlist.json — its path carries
# the same owner/repo, so it is a real origin, not a host-less one).
_GITHUB_HOSTS = {"github.com", "codeload.github.com", "raw.githubusercontent.com"}


def github_origin(pack_url):
    """owner/repo lowercased when `pack_url` is a github.com or
    codeload.github.com link (the pack's origin, §3.3 — the repo, never a
    tag or release filename); None for every other host (gist/raw/Drive)."""
    if not pack_url:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(pack_url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in _GITHUB_HOSTS:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0].lower(), parts[1].lower()
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"


def mep_id_from_meta(mep_meta):
    """The pack's declared `id` (ADR-0140 source (1)) from mep-meta: the
    `pack_id` the workflow recorded, else the recipe `pack.id` the classify
    step transcribed from the pack's own pack.json. Lowercased and validated
    against SLUG; None when absent or not a valid slug."""
    if not isinstance(mep_meta, dict):
        return None
    candidate = mep_meta.get("pack_id")
    if not candidate:
        recipe = mep_meta.get("recipe")
        pack = recipe.get("pack") if isinstance(recipe, dict) else None
        candidate = pack.get("id") if isinstance(pack, dict) else None
    if not isinstance(candidate, str):
        return None
    slug = candidate.strip().lower()
    return slug if SLUG.match(slug) else None


def game_slug(game_name):
    """The ADR-0143 game component of a `{origin}:{game}` pack_id: the
    game identity lowercased with runs of non-`[a-z0-9]` folded to a single
    hyphen (e.g. "Dr_Mario" -> "dr-mario", "Super Mario Bros." ->
    "super-mario-bros", "1942" -> "1942"). None for an empty/whitespace-only
    name — a nameless game can only fall back to the bare origin."""
    if not game_name:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", str(game_name).strip().lower()).strip("-")
    return slug or None


def _meta_game(mep_meta):
    """The ADR-0143 game identity recorded on mep-meta by the validate
    pipeline (`game`), when present; None otherwise."""
    if isinstance(mep_meta, dict):
        game = mep_meta.get("game")
        return game if isinstance(game, str) and game.strip() else None
    return None


def resolve_pack_id(pack_url, mep_meta, issue_number, game=None):
    """ADR-0140/0143 pack_id resolution, first match wins:
    (1) the pack's declared `id` (from mep-meta), else
    (2) `{owner}/{repo}:{game-slug}` for github.com / codeload.github.com
        pack URLs when a game identity is known (ADR-0143: one catalog slot
        per game — `game` from the caller, else the `game` mep-meta records;
        the bare `owner/repo` stays the fallback when neither names one), else
    (3) `issue-{n}` of the accepted submission.
    Returns (pack_id, source) with source one of "id"/"owner-repo"/"issue"."""
    declared = mep_id_from_meta(mep_meta)
    if declared:
        return declared, "id"
    origin = github_origin(pack_url)
    if origin:
        game = game or _meta_game(mep_meta)
        if game:
            slug = game_slug(game)
            if slug:
                return f"{origin}:{slug}", "owner-repo"
        return origin, "owner-repo"
    return f"issue-{issue_number}", "issue"


def apply_mei_identity(entry, pack_url, issue_number, mep_meta, votes):
    """Additive MEI MAY fields (P.2, ADR-0140): `pack_id` (resolved id ->
    owner/repo -> issue-n), `content_id` (ADR-0139 tree/composite hash) and
    `votes` (community 👍 count, non-normative like `issue`). Each omitted
    when unknown/absent — never emitted empty. Unknown-field ignore is
    already required by MEI v1.1, so adding these needs no schema bump."""
    pack_id, _ = resolve_pack_id(pack_url, mep_meta, issue_number)
    if pack_id:
        entry["pack_id"] = pack_id
    content_id = (mep_meta or {}).get("content_id")
    if content_id:
        entry["content_id"] = content_id
    if isinstance(votes, int) and votes >= 0:
        entry["votes"] = votes


def pack_origin(pack_url, issue_author):
    """The origin a pack_id is bound to (§3.3): the pack URL's owner/repo for
    hosts that have one, else the GitHub login that opened the issue. A later
    submission claiming an existing pack_id from a DIFFERENT origin is not a
    revision — it never competes for the slot (see bound-origin check in the
    catalog generator)."""
    origin = github_origin(pack_url)
    if origin:
        return origin
    return (issue_author or "").strip().lower() or None


def compare_semver(a, b):
    """Three-way comparison of two `x.y.z` versions (numeric components);
    None when either is not a comparable semver (absent, or not x.y.z — a
    hd-legacy pack has no version)."""
    if not a or not b:
        return None
    pa = tuple(int(x) for x in str(a).split(".") if x.isdigit())
    pb = tuple(int(x) for x in str(b).split(".") if x.isdigit())
    if len(pa) != 3 or len(pb) != 3:
        return None
    return (pa > pb) - (pa < pb)


def slot_winner(candidates):
    """PRD §3.6: among `candidates` sharing one pack_id, the first rule that
    decides picks the slot occupant: (1) semver of `version` when both are
    comparable — higher wins; (2) `validated_at` — later wins; (3) issue
    number — higher wins. `candidates` is an iterable of dicts each carrying
    `version`, `validated_at` (ISO string or None) and `issue_number`.
    Returns the winning dict, or None for an empty input."""
    best = None
    for candidate in candidates:
        if best is None:
            best = candidate
            continue
        version_cmp = compare_semver(best.get("version"), candidate.get("version"))
        if version_cmp is not None and version_cmp != 0:
            if version_cmp < 0:
                best = candidate
            continue
        # Rule 2: validated_at (ISO 8601 strings compare lexicographically).
        best_at = best.get("validated_at") or ""
        cand_at = candidate.get("validated_at") or ""
        if cand_at != best_at:
            if cand_at > best_at:
                best = candidate
            continue
        # Rule 3: issue number.
        if (candidate.get("issue_number") or 0) > (best.get("issue_number") or 0):
            best = candidate
    return best


def select_catalog_rows(candidates):
    """PRD §3.3/§3.6 over the accepted items: returns (kept, reasons) where
    `kept` is the subset of `candidates` that occupies the official catalog
    (one live row per pack_id, byte-duplicates and foreign-origin claims
    excluded) and `reasons` maps each dropped candidate's issue number to a
    (reason, anchor) pair — ("duplicate", keeper_issue) for the same
    content_id under another pack_id, ("origin", bound_origin) for a
    different-origin claim on an existing pack_id, ("slot", winner_issue)
    for a same-origin revision that lost §3.6.

    Each candidate is a dict carrying at least: `issue_number`, `pack_id`,
    `content_id` (str or None), `version` (str or None), `validated_at`
    (str or None), `origin` (str or None). Deterministic: candidates are
    processed in validated_at then issue-number order, so "the existing row
    wins" (§3.3 byte-duplicate) is the earliest-validated one."""
    ordered = sorted(candidates,
        key=lambda c: ((c.get("validated_at") or ""), (c.get("issue_number") or 0)))
    content_seen = {}
    grouped = {}
    kept = []
    reasons = {}
    for candidate in ordered:
        issue = candidate.get("issue_number")
        content_id = candidate.get("content_id")
        if content_id and content_id in content_seen:
            reasons[issue] = ("duplicate", content_seen[content_id])
            continue
        if content_id:
            content_seen[content_id] = issue
        grouped.setdefault(candidate.get("pack_id"), []).append(candidate)
        kept.append(candidate)
    # Content-dedup pass (above) is global; now resolve per pack_id: drop
    # foreign-origin claims, then the single §3.6 slot winner survives.
    for pack_id, members in grouped.items():
        bound_origin = None
        same_origin = []
        for candidate in members:
            origin = candidate.get("origin")
            if bound_origin is None:
                bound_origin = origin
                same_origin.append(candidate)
            elif origin == bound_origin:
                same_origin.append(candidate)
            else:
                reasons[candidate.get("issue_number")] = ("origin", bound_origin)
        winner = slot_winner(same_origin)
        for candidate in same_origin:
            if candidate is not winner:
                reasons[candidate.get("issue_number")] = ("slot", winner.get("issue_number"))
    return [c for c in kept if c.get("issue_number") not in reasons], reasons
