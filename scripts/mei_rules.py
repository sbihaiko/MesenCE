#!/usr/bin/env python3
"""mei_rules — dependency-free leaf holding the MEI v1.1 constraint set
(ADR-0138 §28): the ROM-id/system/hash/semver regexes and the kind-
conditional required-field logic that `validate-specs.py`'s `validate_mei`
and the community-pack catalog generator each used to mirror by hand, plus
the MEI v1.3 §2.5 identity-field shapes (`PACK_ID`, `CONTENT_ID_HEX`,
`mei_identity_field_errors`) for the additive `pack_id`/`content_id`/`votes`.
Also holds the Status-literal -> kind mapping (`STATUS_TO_KIND`, §29) and
its resolver (`resolve_kind`), so both the generator and any workflow-side
parity check import one shared pairing instead of duplicating it. stdlib
only — no imports of any other `scripts/` module, so both call sites can
depend on this leaf without a cycle (ADR-0138 §24 convention).
"""
from __future__ import annotations

import re

SYSTEMS = {"nes", "gb", "gbc", "sms", "gg", "sg1000", "coleco", "snes"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
SHA1_UPPER = re.compile(r"^[0-9A-F]{40}$")
CRC32_UPPER = re.compile(r"^[0-9A-F]{8}$")
MD5_UPPER = re.compile(r"^[0-9A-F]{32}$")
SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")
MEI_KINDS = {"mep", "hd-legacy"}

# MEI v1.3 §2.5 `pack_id` (ADR-0140/0143): one of the three catalog sources,
# lowercase — a declared MEP `id` slug `[a-z0-9][a-z0-9-]{2,63}`,
# `owner/repo` optionally suffixed `:game-slug`, or `issue-N`. The client-only
# `local:<container>` fallback (ADR-0140 source 4) never appears in an index.
PACK_ID = re.compile(
    r"^(?:[a-z0-9][a-z0-9-]{2,63}"
    r"|[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9._-]*(?::[a-z0-9]+(?:-[a-z0-9]+)*)?"
    r"|issue-[1-9][0-9]*)$"
)
# MEI v1.3 §2.5 `content_id` (ADR-0139): the hasher's `sha256().hexdigest()`,
# i.e. exactly 64 LOWERCASE hex digits (unlike `sha256`, which reads
# case-insensitively).
CONTENT_ID_HEX = re.compile(r"^[0-9a-f]{64}$")

# Board Status literals stay exactly as configured on the GitHub Project
# (Portuguese literals per CLAUDE.md) -- never translated here. This is the
# sole definition of the Status->kind pairing in scripts/ (§29); anything
# else that needs it imports STATUS_TO_KIND or calls resolve_kind rather
# than re-deriving the pairing from the literals.
STATUS_TO_KIND = {
    "Aceito (MEP completo)": "mep",
    "Aceito parcial (HD Mesen)": "hd-legacy",
}


def required_mei_pack_fields(kind):
    """The `packs[]` fields MEI v1.1 requires for a given `kind` (§2.2/§2.3).

    A "hd-legacy" pack predates MEP and needs no `version`/`mep`; any other
    kind (including `None`, the schema default) does.
    """
    required = ["name", "game", "system", "rom", "url", "sha256"]
    if kind != "hd-legacy":
        required += ["version", "mep"]
    return required


def mei_entry_conforms(entry, kind):
    """Whether `entry` (a MEI `packs[]` entry under construction) already
    carries every field `required_mei_pack_fields(kind)` demands -- present
    for all of them, non-empty for all but `rom`. This is the single §28
    conformance predicate: `mei_catalog_entry` and the generator facade
    re-export it rather than defining their own.

    Used by catalog assembly to self-check an entry before it is kept
    (§28) -- a "mep"-kind entry that is missing `version`/`mep` (e.g. its
    mep-meta recipe was absent or lacked a `pack` object) fails here and
    must be dropped rather than silently relabeled as "hd-legacy".
    """
    if kind is not None and kind not in MEI_KINDS:
        return False
    for field in required_mei_pack_fields(kind):
        if field not in entry:
            return False
        # `rom` is an object whose `sha1` MAY be absent (MEI v1.1 §2.3), so
        # `{}` is a wire-valid value -- presence, not truthiness, is checked.
        if field != "rom" and not entry[field]:
            return False
    return True


def resolve_kind(mep_meta, status):
    """Derives MEI `kind` mep-meta-first, Status-literal-fallback (§29).

    `mep_meta` is the parsed `<!-- mep-meta -->` payload (a dict, or
    `None`/anything falsy when absent/unparseable). A valid `kind` there
    (one of MEI_KINDS) wins; otherwise falls back to
    `STATUS_TO_KIND.get(status)`. Returns `None` -- never a kind-less
    resolution masquerading as a real kind -- when neither source yields
    one, e.g. an unmapped Status with no usable mep-meta `kind`.
    """
    if isinstance(mep_meta, dict):
        meta_kind = mep_meta.get("kind")
        if meta_kind in MEI_KINDS:
            return meta_kind
    return STATUS_TO_KIND.get(status)


def mei_identity_field_errors(entry):
    """MEI v1.3 §2.5 shape checks for the additive `pack_id`/`content_id`/
    `votes` of one `packs[]` entry. Each field MAY be absent; when present it
    must be a non-empty `PACK_ID` string, a `CONTENT_ID_HEX` string, or a
    non-negative JSON integer (a bool is not an integer). Returns a list of
    human-readable messages, empty when the entry conforms — shared by
    `validate-specs.py` (rejects) and `mei_catalog_entry.build_pack_entry`
    (omits the offending MAY field) so the producer never emits what the
    validator rejects (ADR-0138 §28 single-definition rule).
    """
    errors = []
    if "pack_id" in entry:
        pack_id = entry["pack_id"]
        if not isinstance(pack_id, str) or not PACK_ID.match(pack_id):
            errors.append(f"pack_id must be a lowercase slug, owner/repo[:game-slug] or issue-N string, got {pack_id!r}")
    if "content_id" in entry:
        content_id = entry["content_id"]
        if not isinstance(content_id, str) or not CONTENT_ID_HEX.match(content_id):
            errors.append(f"content_id must be exactly 64 lowercase hex digits, got {content_id!r}")
    if "votes" in entry:
        votes = entry["votes"]
        if isinstance(votes, bool) or not isinstance(votes, int) or votes < 0:
            errors.append(f"votes must be a non-negative integer, got {votes!r}")
    return errors
