#!/usr/bin/env python3
"""mei_catalog_entry — dependency-free leaf module that assembles one MEI
v1.1 `packs[]` entry (ADR-0138 F6.3, §26-27) out of already-fetched data.

No `gh`/network I/O of its own: `generate_community_pack_catalog.py` fetches
the Project item, the issue, and the `<!-- mep-meta -->` comment body (via
`mep_meta_parser.parse_mep_meta`) and hands the resulting plain dicts to the
functions here. Kept separate per scripts/AGENTS.md's split convention — a
leaf module both the generator and a future test import, never the reverse
(ADR-0138 Clarification §24).

stdlib only.
"""
from __future__ import annotations

MEI_VERSION = "1.1.0"
CATALOG_NAME = "MesenCE community packs"
MAINTAINER = "sbihaiko"

# Board Status literals stay exactly as configured on the GitHub Project
# (Portuguese literals per CLAUDE.md) — never translated here.
STATUS_MEP_COMPLETO = "Aceito (MEP completo)"
STATUS_HD_PARCIAL = "Aceito parcial (HD Mesen)"

def item_status(item):
    """Defensive lookup of the item's Status (same coverage gap as below)."""
    return item.get("status") or item.get("Status") or ""


def item_issue_number(item):
    """Defensive lookup of the source issue number, trying the plausible formats."""
    content = item.get("content") or {}
    return content.get("number") or item.get("number") or item.get("issue_number")


def item_pack_url(item):
    """Defensive lookup of the item's Pack URL field.

    Same unconfirmed per-item-key-name COVERAGE GAP documented in
    generate_community_pack_catalog.py's fetch_accepted_items docstring
    applies here: the Project had zero items at write time, so these key
    names are not confirmed against real data. `dict.get` (never direct
    indexing) so an unexpected shape yields a defensive, non-crashing
    `None` instead of a `KeyError`.
    """
    return item.get("packUrl") or item.get("Pack URL") or item.get("pack_url")

def item_pack_hash(item):
    """Defensive lookup of the item's Pack Hash field (same gap as above)."""
    return item.get("packHash") or item.get("Pack Hash") or item.get("pack_hash")

def item_rom_sha1(item):
    """Defensive lookup of the item's ROM SHA1 field (same gap as above)."""
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
    entries = []
    for dep in deps:
        entry = {"id": dep.get("id"), "license": dep.get("license") or "unknown"}
        if dep.get("sha256"):
            entry["sha256"] = dep["sha256"]
        if dep.get("size") is not None:
            entry["size"] = dep["size"]
        hints = dep.get("hints") or []
        if hints:
            entry["url"] = hints[0]
        entries.append(entry)
    return entries

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

def build_catalog(entries, updated):
    """Wraps entries into the top-level MEI v1.1 catalog document (§26)."""
    return {
        "mei": MEI_VERSION,
        "name": CATALOG_NAME,
        "maintainer": MAINTAINER,
        "updated": updated,
        "packs": entries,
    }
