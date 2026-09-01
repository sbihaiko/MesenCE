# ADR-0139: content_id: canonical hash of the resolved pack tree, recipe composite, two implementations

- Status: accepted
- Date: 2026-08-28

## Context
the consolidated PRD, Part B §3.2 (accepted product text, 2026-08-28). The catalog's Pack Hash / MEI sha256 / mep-meta source_sha256 is the download wrapper, not the pack: after ADR-0120/0121 discovery (and a MEP Recipe when present) the host loads a subset of the zip. Two wrappers of the same tree must be one revision; two recipes on one primary zip must be two revisions. The client needs the same value to detect updates (§3.6) and to merge a user-dropped container with a catalog install (§5). Product constraint: same loaded files ⇒ same content_id; wrapper-only change ⇒ same content_id; any loaded-file change ⇒ new content_id.

## Decision
content_id = SHA-256 over a canonical manifest of the discovered pack root: entries sorted by byte-wise UTF-8 path relative to the root, using '/' separators; for each entry the path, a single byte-length, and the SHA-256 of the file bytes; directories, zip entry metadata (mtime, permissions, comments) and files outside the discovered root (__MACOSX/, .DS_Store, README, screenshots) are excluded; pack.json is included with its 'version' key removed before hashing so a label-only bump is not a new revision; no newline folding (bytes are hashed as-is). With a recipe: content_id = SHA-256 of the string primary_tree_hash + '\n' + recipe_hash + '\n' + dep sha256s sorted by dep id (declared digests, so CI needs no user_supplied bytes). Two implementations, one normative reference (same rule as ADR-0138 §39): scripts/ (Python, used by mep_lint / community-pack-validate, writes content_id to mep-meta) and Core (C++, MepPackManager for local containers, MepRecipeInstaller at install time from the primary bytes, stored in .mep-install.json — never re-derived from the installed output tree). A parity fixture under docs/specs/golden/ (same tree in two wrappers ⇒ equal ids; two recipes on one primary ⇒ different ids) is run by both sides. Slice: P.1 of the consolidated PRD, Part B.

## Consequences

Implementation state (verified 2026-09-01):
- Normative hasher: `scripts/mep_content_id.py` (`compute_tree_content_id` :71, `compute_recipe_content_id` :92; excluded segments/basenames :14-22, `pack.json` canonicalized without `version` :56-61). Surfaced by `mep_lint --content-id` (`scripts/mep_lint.py:40-43`, `compute_content_id` :578) and written to mep-meta by the validate workflow (`.github/workflows/community-pack-validate.yml:313-322`, `meta["content_id"]` :1036).
- Core hasher: `Core/Shared/EnhancementPacks/MepContentId.{h,cpp}` (`ComputeTree` :246, `ComputeRecipe` :273, `ComputeFolder` :286). `MepRecipeInstaller.cpp:486-503` computes the recipe composite from the primary bytes at install time and writes `pack_id`/`content_id` into `.mep-install.json` (:389-392); `MepPackManager::ReadInstallIdentity` (:585-599) only reads that stamp back.
- Parity golden `docs/specs/golden/mep-content-id.json`, run by `scripts/test_mep_content_id_golden.py` (Makefile:284) and by `TestContentIdGoldenParity` in `scripts/core_unit_tests.cpp:805-814` (Makefile:320); `scripts/test_mep_content_id.py` (Makefile:274) covers the two-wrappers / two-recipes cases.
- The catalog carries `content_id` on every row (`docs/community-packs.json`, 11 rows) and it is the client update trigger (ADR-0141, `UI/Logic/CommunityCatalogUpdateDecision.cs`) and the §5 merge key (`UI/Logic/PackPreferenceResolver.cs:64-80`).
- ADR-0147 reuses `ComputeFolder` (exported as `GetMepContentId`, `UI/Interop/EmuApi.cs:143-148`) as the local-edit baseline of an installed `mep/` tree.
Not implemented: the Decision's "MepPackManager for local containers" — a stamp-less local drop gets no computed `content_id` (empty identity, `local:<container>` fallback, `MepPackManager.cpp:589-590`); the CI-side `content_id` is the tree form only (the recipe composite is computed only by the Core installer).

## Alternatives

- Hash the download wrapper (catalog `sha256` / mep-meta `source_sha256`): rejected — two wrappers of one tree would be two revisions, and one wrapper with two recipes one revision (Context).
- Hash the installed output tree (re-derive after install): rejected — output depends on user-supplied deps and host rewrites, so CI and client would never agree; the composite is stored once at install time (`MepRecipeInstaller.cpp:486-490`).
- Include `pack.json` `version` in the hash: rejected — a label-only bump would force a reinstall (Decision).
- Single implementation (Python only, or Core only): rejected — CI has no Core binary and the client has no Python; the ADR-0138 §39 two-implementations + shared golden rule was reused instead.
- Include zip metadata (mtime, permissions) or fold newlines: rejected — wrapper noise, not content.
