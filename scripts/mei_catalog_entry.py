#!/usr/bin/env python3
"""mei_catalog_entry — MEI v1.1 `packs[]` entry assembly for the community
pack catalog (ADR-0138 §26/§27/§28, split off `generate_community_pack_
catalog.py` per §35's 200-line-per-file guardrail). Depends only on the
stdlib-only leaf `mei_rules` (never on `community_pack_markdown` or the
facade -- §24). `build_pack_entry` derives `kind` via `mei_rules.
resolve_kind` (§29); `build_catalog` self-checks each entry via this
module's own `mei_entry_conforms` (§28), built on `mei_rules.required_
mei_pack_fields`/`MEI_KINDS` but matching `validate_mei`'s real semantics:
presence for every required field, truthy for all but `rom` (§2.3: `rom.
sha1` MAY be absent). `STATUS_MEP_COMPLETO`/`STATUS_HD_PARCIAL`/
`kind_from_status` derive FROM `mei_rules.STATUS_TO_KIND` (never a second
pairing -- verify_status_kind_parity.sh, §29).

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


def mei_entry_conforms(entry, kind):
    """Whether `entry` conforms to §28 for `kind`: every field named by
    `mei_rules.required_mei_pack_fields(kind)` MUST be present, truthy for
    all but `rom`. Kind validity reuses `mei_rules.MEI_KINDS`.
    """
    if kind is not None and kind not in mei_rules.MEI_KINDS:
        return False
    for field in mei_rules.required_mei_pack_fields(kind):
        if field not in entry:
            return False
        if field != "rom" and not entry[field]:
            return False
    return True


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
    (not mep-meta's own stripped `deps`, which lacks `license` -- MEI-v1
    §2.3/MEP-recipe-v1 §3.3). Returns None (not `[]`) when there is
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
    """Returns (deps, recipe, recipe_hash, recipe_ok, mismatch); a `source_
    sha256`/Pack Hash disagreement means the field wins -- deps/recipe
    omitted, `mismatch` True (ADR-0138 §18, never fatal).
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
    """Normalizes the "ROM SHA1" field to 40-UPPERCASE-hex via `mei_rules.
    SHA1_UPPER`. Returns None when empty/malformed -- `rom.sha1` is
    optional in MEI v1.1, so the caller omits it.
    """
    if not rom_sha1:
        return None
    candidate = rom_sha1.strip().upper()
    return candidate if mei_rules.SHA1_UPPER.match(candidate) else None


def _entry_base(issue_number, game, system, license_, pack_url, pack_hash, rom_sha1, kind):
    """Builds the fields every entry has; `rom` is always present (§2.3:
    key required, not a non-empty value).
    """
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
    """Extracts `pack.version`/`pack.mep` from a mep-meta recipe's `pack`
    object (MEP-recipe-v1 §3.1); each None when absent/malformed.
    """
    pack = recipe.get("pack") if isinstance(recipe, dict) else None
    if not isinstance(pack, dict):
        return None, None
    return pack.get("version"), pack.get("mep")


def build_pack_entry(issue_number, game, system, license_, pack_url, pack_hash, rom_sha1, status, mep_meta):
    """Assembles one MEI v1.1 packs[] entry (§26/§27). `kind` comes from
    `mei_rules.resolve_kind` (§29). Returns (entry, mismatch) -- see
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
    """Whether this item has everything `validate_mei` requires of a
    `packs[]` entry's `url`/`sha256`/`system`, reusing `mei_rules.SYSTEMS`/
    `SHA256_HEX`. False when Pack URL/Hash are malformed/absent.
    """
    return (
        bool(pack_url) and pack_url.startswith("https://")
        and bool(pack_hash) and bool(mei_rules.SHA256_HEX.match(pack_hash))
        and system in mei_rules.SYSTEMS
    )


def build_catalog(entries, updated):
    """Wraps entries into the top-level MEI v1.1 catalog document (§26),
    self-checking each via `mei_entry_conforms` first (§28).
    """
    packs = [e for e in entries if mei_entry_conforms(e, e.get("kind"))]
    return {
        "mei": MEI_VERSION,
        "name": CATALOG_NAME,
        "maintainer": MAINTAINER,
        "updated": updated,
        "packs": packs,
    }
