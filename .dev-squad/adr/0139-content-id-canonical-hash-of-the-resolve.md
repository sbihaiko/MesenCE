# ADR-0139: content_id: canonical hash of the resolved pack tree, recipe composite, two implementations

- Status: accepted
- Date: 2026-08-28

## Context
PRD-player-shell.md §3.2 (accepted product text, 2026-08-28). The catalog's Pack Hash / MEI sha256 / mep-meta source_sha256 is the download wrapper, not the pack: after ADR-0120/0121 discovery (and a MEP Recipe when present) the host loads a subset of the zip. Two wrappers of the same tree must be one revision; two recipes on one primary zip must be two revisions. The client needs the same value to detect updates (§3.6) and to merge a user-dropped container with a catalog install (§5). Product constraint: same loaded files ⇒ same content_id; wrapper-only change ⇒ same content_id; any loaded-file change ⇒ new content_id.

## Decision
content_id = SHA-256 over a canonical manifest of the discovered pack root: entries sorted by byte-wise UTF-8 path relative to the root, using '/' separators; for each entry the path, a single byte-length, and the SHA-256 of the file bytes; directories, zip entry metadata (mtime, permissions, comments) and files outside the discovered root (__MACOSX/, .DS_Store, README, screenshots) are excluded; pack.json is included with its 'version' key removed before hashing so a label-only bump is not a new revision; no newline folding (bytes are hashed as-is). With a recipe: content_id = SHA-256 of the string primary_tree_hash + '\n' + recipe_hash + '\n' + dep sha256s sorted by dep id (declared digests, so CI needs no user_supplied bytes). Two implementations, one normative reference (same rule as ADR-0138 §39): scripts/ (Python, used by mep_lint / community-pack-validate, writes content_id to mep-meta) and Core (C++, MepPackManager for local containers, MepRecipeInstaller at install time from the primary bytes, stored in .mep-install.json — never re-derived from the installed output tree). A parity fixture under docs/specs/golden/ (same tree in two wrappers ⇒ equal ids; two recipes on one primary ⇒ different ids) is run by both sides. Slice: P.1 of PRD-player-shell.md.

## Consequences


## Alternatives

