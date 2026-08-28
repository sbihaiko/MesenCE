#!/usr/bin/env python3
"""mei_catalog_entry — MEI v1.1 `packs[]` entry assembly for the community
pack catalog (ADR-0138 §26/§27/§28, split out of `generate_community_pack_
catalog.py` per §35's 200-line-per-file guardrail).

Depends only on the stdlib-only leaf `mei_rules` (never on
`community_pack_markdown` or the facade -- ADR-0138 §24, mirroring
`mep_recipe_common.py`). `build_pack_entry` derives `kind` via
`mei_rules.resolve_kind` (mep-meta first, Status fallback, §29);
`build_catalog` self-checks every entry through `mei_rules.mei_entry_conforms`
before it is kept (§28), dropping a "mep"-kind entry missing `version`/`mep`
rather than relabeling it "hd-legacy". `STATUS_MEP_COMPLETO`/
`STATUS_HD_PARCIAL`/`kind_from_status` are derived FROM
`mei_rules.STATUS_TO_KIND` (never a second pairing -- verify_status_kind_
parity.sh, §29) so the facade's back-compat re-export (§24) keeps working.

stdlib only.
"""
from __future__ import annotations

import mei_rules

MEI_VERSION = "1.1.0"
CATALOG_NAME = "MesenCE community packs"
MAINTAINER = "sbihaiko"

# Derived FROM mei_rules.STATUS_TO_KIND -- never a second, independent pair.
_KIND_TO_STATUS = {kind: status for status, kind in mei_rules.STATUS_TO_KIND.items()}
STATUS_MEP_COMPLETO = _KIND_TO_STATUS["mep"]
STATUS_HD_PARCIAL = _KIND_TO_STATUS["hd-legacy"]


def kind_from_status(status):
    """Facade-compatible Status->kind lookup on `mei_rules.STATUS_TO_KIND`."""
    return mei_rules.STATUS_TO_KIND.get(status)


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
    """Extracts MEI `deps[]` from mep-meta's embedded `recipe.sources.deps`
    (not mep-meta's own top-level stripped `deps`, which lacks `license` --
    MEI-v1 §2.3/MEP-recipe-v1 §3.3). Returns None (not `[]`) when there is
    nothing to report, so the caller can omit the key.
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
    """Returns (deps, recipe, recipe_hash, recipe_ok, mismatch). ADR-0138
    §18 "two stores, one rule": when mep-meta's `source_sha256` disagrees
    with the Project "Pack Hash" field, the field wins -- deps/recipe are
    omitted and `mismatch` is True (never a fatal error for the whole run).
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


def normalized_rom_sha1(rom_sha1):
    """Normalizes the Project "ROM SHA1" field to 40-UPPERCASE-hex, reusing
    `mei_rules.SHA1_UPPER` rather than a second, locally-declared regex.
    Human-entered tools (sha1sum/shasum) emit lowercase, so this
    upper-cases before checking shape. Returns None (not an invalid
    string) when empty/malformed -- `rom.sha1` is optional in MEI v1.1, so
    the caller omits it rather than emit an entry `validate_mei` rejects.
    """
    if not rom_sha1:
        return None
    candidate = rom_sha1.strip().upper()
    return candidate if mei_rules.SHA1_UPPER.match(candidate) else None


def _entry_base(issue_number, game, system, license_, pack_url, pack_hash, rom_sha1, kind):
    """Builds the fields every entry has regardless of `kind` or mep-meta."""
    sha1 = normalized_rom_sha1(rom_sha1)
    rom = {"sha1": sha1} if sha1 else {}
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


def pack_version_fields(recipe):
    """Extracts `pack.version`/`pack.mep` from a mep-meta recipe document's
    `pack` object (MEP-recipe-v1 §3.1) for a kind=="mep" entry. Returns
    (version, mep), each None when absent/malformed -- `mei_rules.
    mei_entry_conforms` enforces both being present for a "mep" entry.
    """
    pack = recipe.get("pack") if isinstance(recipe, dict) else None
    if not isinstance(pack, dict):
        return None, None
    return pack.get("version"), pack.get("mep")


def build_pack_entry(issue_number, game, system, license_, pack_url, pack_hash, rom_sha1, status, mep_meta):
    """Assembles one MEI v1.1 packs[] entry (ADR-0138 §26/§27). `kind`
    comes from `mei_rules.resolve_kind` (mep-meta first, Status fallback,
    §29), never Status alone. Returns (entry, mismatch) -- see
    `recipe_fields` for `mismatch`.
    """
    kind = mei_rules.resolve_kind(mep_meta, status)
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
    if kind == "mep":
        version, mep_version = pack_version_fields(recipe)
        if version:
            entry["version"] = version
        if mep_version:
            entry["mep"] = mep_version
    _apply_mep_meta_passthrough(entry, mep_meta)
    return entry, mismatch


def mei_entry_preconditions_ok(pack_url, pack_hash, system):
    """Whether this item has everything `validate_mei` (scripts/validate-
    specs.py) requires of a `packs[]` entry's `url`/`sha256`/`system`
    (MEI-v1 §2), reusing `mei_rules.SYSTEMS`/`mei_rules.SHA256_HEX` rather
    than a second, locally-declared copy. Returns False when the Project's
    Pack URL/Pack Hash are absent/malformed, or the Console value has no
    MEI-representable system (the Form's "Other" lowercases to "other",
    unmapped falls back to "?" -- neither is in `mei_rules.SYSTEMS`). The
    caller omits the JSON entry rather than emit one `validate_mei`
    rejects; the Markdown row still renders.
    """
    return (
        bool(pack_url) and pack_url.startswith("https://")
        and bool(pack_hash) and bool(mei_rules.SHA256_HEX.match(pack_hash))
        and system in mei_rules.SYSTEMS
    )


def build_catalog(entries, updated):
    """Wraps entries into the top-level MEI v1.1 catalog document (§26),
    self-checking each through `mei_rules.mei_entry_conforms` first (§28)
    -- a non-conforming entry is dropped here even if a caller forgot to
    filter it, rather than reaching docs/community-packs.json.
    """
    packs = [e for e in entries if mei_rules.mei_entry_conforms(e, e.get("kind"))]
    return {
        "mei": MEI_VERSION,
        "name": CATALOG_NAME,
        "maintainer": MAINTAINER,
        "updated": updated,
        "packs": packs,
    }
