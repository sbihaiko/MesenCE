#!/usr/bin/env python3
"""mep_content_id — ADR-0139 `content_id`: canonical hash of the resolved pack
tree, or of the primary tree + recipe + declared deps when a recipe exists.

Normative reference for P.1 (PRD Part B §3.2). Two implementations must
agree on this value: `scripts/` (CI, this module — normative) and the Core
(`MepPackManager` for local containers, `MepRecipeInstaller` at install time).
The parity fixture under `docs/specs/golden/` is run by both sides.

No-recipe form — `compute_tree_content_id(entries)`:
    content_id = hex SHA-256 over a canonical manifest of the discovered pack
    root. `entries` is an iterable of `(rel_path, data_bytes)` for every file
    under the root (directories and zip entry metadata are not passed in).
    The manifest is the entries sorted by byte-wise UTF-8 path ('/' separators);
    for each entry: the path bytes, one byte = the path length (paths must be
    < 256 bytes), then the 32-byte SHA-256 of the entry payload. Entries whose
    path contains a `__MACOSX` or `screenshots` segment, or whose basename is
    `.DS_Store` or starts with `README`, are excluded — they are the artefacts
    ADR-0139 names as "outside the discovered root". `pack.json` is hashed as
    canonical JSON (sort_keys, compact separators) with its `version` key
    removed, so a label-only bump is not a new revision; every other file is
    hashed byte-for-byte (no newline folding).

Recipe form — `compute_recipe_content_id(primary_tree_hash, recipe_hash,
dep_hashes)`:
    content_id = hex SHA-256 of `primary_tree_hash + '\\n' + recipe_hash` plus a
    `'\\n'`-joined line per dep digest, sorted by dep id. CI can compute this
    from the primary zip + the recipe's declared digests without fetching
    `user_supplied` deps; the client computes the same function at install time
    and stores it in `.mep-install.json` (never re-derived from the installed
    output tree).

Usage:
    python3 -c "import mep_content_id; ..."
"""
from __future__ import annotations

import hashlib
import json

# Path segments / basenames excluded from the tree hash (ADR-0139): the
# artefacts it names as "outside the discovered root".
_EXCLUDED_SEGMENTS = {"__MACOSX", "screenshots"}
_EXCLUDED_BASENAMES = {".DS_Store"}


def _is_excluded(rel_path: str) -> bool:
    """True when the entry is one ADR-0139 keeps out of the content_id."""
    parts = rel_path.split("/")
    if any(seg in _EXCLUDED_SEGMENTS for seg in parts):
        return True
    basename = parts[-1]
    return basename in _EXCLUDED_BASENAMES or basename.startswith("README")


def _canonical_pack_json(data: bytes) -> bytes:
    """pack.json payload: canonical JSON (sort_keys, compact) without 'version',
    so a label-only bump is not a new revision while other pack.json changes
    still are."""
    obj = json.loads(data.decode("utf-8"))
    obj.pop("version", None)
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _entry_payload(rel_path: str, data: bytes) -> bytes:
    if rel_path == "pack.json" or rel_path.endswith("/pack.json"):
        return _canonical_pack_json(data)
    return data


def compute_tree_content_id(entries) -> str:
    """Hex SHA-256 of the canonical manifest of the resolved pack root.

    `entries`: iterable of `(rel_path, data_bytes)` for the discovered root's
    files. Rel paths use '/' separators, relative to the root. Paths must be
    shorter than 256 bytes (the manifest stores the length in one byte).
    """
    manifest = bytearray()
    for rel_path, data in sorted(entries, key=lambda e: e[0]):
        if _is_excluded(rel_path):
            continue
        payload = _entry_payload(rel_path, data)
        path_bytes = rel_path.encode("utf-8")
        if len(path_bytes) >= 256:
            raise ValueError(f"content_id path too long: {rel_path}")
        manifest += path_bytes
        manifest.append(len(path_bytes))
        manifest += hashlib.sha256(payload).digest()
    return hashlib.sha256(bytes(manifest)).hexdigest()


def compute_recipe_content_id(primary_tree_hash: str, recipe_hash: str, dep_hashes: dict[str, str]) -> str:
    """Hex SHA-256 of the primary tree + recipe + declared dep digests.

    `dep_hashes`: dep id -> hex sha256, as declared by the recipe (CI does not
    need the dep bytes). The dep digests are emitted sorted by dep id, one per
    '\\n' line after the primary/recipe pair."""
    lines = [primary_tree_hash, recipe_hash]
    for dep_id in sorted(dep_hashes):
        lines.append(dep_hashes[dep_id])
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
