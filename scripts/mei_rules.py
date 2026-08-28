#!/usr/bin/env python3
"""mei_rules — dependency-free leaf holding the MEI v1.1 constraint set
(ADR-0138 §28): the ROM-id/system/hash/semver regexes and the kind-
conditional required-field logic that `validate-specs.py`'s `validate_mei`
and the community-pack catalog generator each used to mirror by hand.
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
    carries every field `required_mei_pack_fields(kind)` demands, matching
    `validate_mei`'s own semantics field-by-field: `rom` only needs to be
    *present* (an empty dict is valid -- MEI v1.1 makes `rom.sha1` MAY-be-
    absent regardless of `kind`, and `validate_mei` itself only checks
    `"rom" in p`, never its truthiness), while every other required field
    (`name`/`game`/`system`/`url`/`sha256`, plus `version`/`mep` for a
    "mep"-kind entry) must additionally be non-empty ("truthy").

    Used by catalog assembly to self-check an entry before it is kept
    (§28) -- a "mep"-kind entry that is missing `version`/`mep` (e.g. its
    mep-meta recipe was absent or lacked a `pack` object) fails here and
    must be dropped rather than silently relabeled as "hd-legacy".
    """
    if kind is not None and kind not in MEI_KINDS:
        return False
    for field in required_mei_pack_fields(kind):
        if field == "rom":
            if field not in entry:
                return False
            continue
        if not entry.get(field):
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
