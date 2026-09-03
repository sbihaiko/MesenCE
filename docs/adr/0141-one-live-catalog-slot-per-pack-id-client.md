# ADR-0141: One live catalog slot per pack_id; client update trigger content_id (amends ADR-0138 §37); no auto-downgrade

- Status: accepted
- Date: 2026-08-28

## Context
the consolidated PRD, Part B §3.6 and §4 (accepted product text, 2026-08-28). The player must never be asked to choose between 1.0 and 1.2 of the same pack; the official catalog must expose one current revision per product. ADR-0138 §37 (accepted) makes F6.4b reinstall when catalog source.sha256 differs from .mep-install.json — that fires on wrapper-only changes and misses the actual revision identity. Yanks and republished older labels must not silently downgrade a user's install. Removal of a pack from the catalog must not interrupt a player.

## Decision
Catalog (CI): one live slot per pack_id. When two candidates compete, the first rule that decides wins: (1) higher semver of pack.json version when both are comparable (an inflated version can win — triage warns, does not block — but only among candidates of the same origin: ADR-0140 origin binding, amendment 2026-08-28, keeps a different-origin submission out of the contest entirely); (2) else later validated_at; (3) else higher issue number. /revalidate rewrites that issue's provenance in place (mep-meta source_sha256, content_id, version, validated_at) but occupies the slot only by this order — a lower semver does not displace a higher one. History stays in mep-meta/git, never a second row. Client (amendment to ADR-0138 §37, superseding its trigger text): reinstall when the catalog slot's content_id differs from .mep-install.json content_id for the chosen pack_id; wrapper-only change (source.sha256 differs, content_id equal) does not reinstall. No automatic downgrade: if the installed semver is greater than the slot's, keep the install; Advanced may offer 'use catalog revision' with confirmation; hd-legacy (no semver) still updates on content_id difference. Pack removed from the catalog: keep install and per-ROM choice, no toast; still visible in Advanced. Reinstall preserves DisabledPacks and per-section flags (keyed by container name, unchanged on update). Sibling folder always wins: no catalog write, update or picker while present. .mep-install.json gains pack_id and content_id next to recipe_hash / source.sha256 / deps / installed_at. Slices: P.2 (CI) and P.6 (client) of the consolidated PRD, Part B.

## Consequences

Implementation state (verified 2026-09-01):
- CI slot rule: `slot_winner` (`scripts/pack_id_rules.py:156-183`: semver → `validated_at` → issue number) inside `select_catalog_rows` (:186), applied by `scripts/generate_community_pack_catalog.py:132-134` when it writes `docs/community-packs.json`/`.md`; origin gating comes from ADR-0140's `pack_origin`. Tests: `scripts/test_pack_id_rules.py`.
- Client trigger: `UI/Logic/CommunityCatalogUpdateDecision.cs` (`Decide` :49-78 — `Updated` on `content_id` difference, `WrapperOnly` when only `sha256` differs, `NoDowngrade` when the installed semver is higher, `RemovedFromCatalog` keeps the install; `ReadStampFields` :83, `CompareSemver` :108), consumed by `UI/Services/CommunityPackInstallCoordinator.cs:203-226` — the silent verdicts return `Skipped`, `Updated` clears and reinstalls (or, per ADR-0147, offers Restore when the `mep/` tree was edited locally).
- `.mep-install.json` gains `pack_id`/`content_id` (`Core/Shared/EnhancementPacks/MepRecipeInstaller.cpp:389-392`); the stamp carries no version, so the no-downgrade guard reads the installed version from `GetMepPackList` column 3 (`CommunityPackInstallCoordinator.cs:226-230`).
- DisabledPacks/per-section flags survive because the container name is unchanged by an update (`CommunityPackInstallCoordinator.cs:196-199`).
- Sibling folder wins: `UI/Logic/PlayerPackPicker.cs:19-22` never opens the picker when a sibling pack is present; the coordinator does not write the catalog install in that case (PRD Part B §4).
- ADR-0138 §37's own text was annotated in place (slice D5) to point here for the trigger.
Not implemented: the Advanced "use catalog revision" confirmation for a `NoDowngrade` install (no such action exists in `UI/`); the client has no separate visibility marker for "removed from catalog" beyond keeping the install.

## Alternatives

- Keep ADR-0138 §37's `source.sha256` trigger: rejected — it fires on wrapper-only repacks and misses a real revision shipped under an unchanged wrapper (Context).
- List every accepted revision as its own row and let the player choose: rejected — the player must never pick between 1.0 and 1.2 of one pack; history lives in mep-meta/git.
- Always follow the catalog (auto-downgrade when a yank republishes an older label): rejected — a user's newer install is kept; only hd-legacy packs (no semver) update on any `content_id` difference.
- Uninstall or toast when a pack leaves the catalog: rejected — removal must not interrupt a player.
- Block an inflated semver in CI: rejected — triage warns, does not block; the origin binding (ADR-0140) is what keeps strangers out of the contest.
