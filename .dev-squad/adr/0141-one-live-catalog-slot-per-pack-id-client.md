# ADR-0141: One live catalog slot per pack_id; client update trigger content_id (amends ADR-0138 §37); no auto-downgrade

- Status: accepted
- Date: 2026-08-28

## Context
the consolidated PRD, Part B §3.6 and §4 (accepted product text, 2026-08-28). The player must never be asked to choose between 1.0 and 1.2 of the same pack; the official catalog must expose one current revision per product. ADR-0138 §37 (accepted) makes F6.4b reinstall when catalog source.sha256 differs from .mep-install.json — that fires on wrapper-only changes and misses the actual revision identity. Yanks and republished older labels must not silently downgrade a user's install. Removal of a pack from the catalog must not interrupt a player.

## Decision
Catalog (CI): one live slot per pack_id. When two candidates compete, the first rule that decides wins: (1) higher semver of pack.json version when both are comparable (an inflated version can win — triage warns, does not block — but only among candidates of the same origin: ADR-0140 origin binding, amendment 2026-08-28, keeps a different-origin submission out of the contest entirely); (2) else later validated_at; (3) else higher issue number. /revalidate rewrites that issue's provenance in place (mep-meta source_sha256, content_id, version, validated_at) but occupies the slot only by this order — a lower semver does not displace a higher one. History stays in mep-meta/git, never a second row. Client (amendment to ADR-0138 §37, superseding its trigger text): reinstall when the catalog slot's content_id differs from .mep-install.json content_id for the chosen pack_id; wrapper-only change (source.sha256 differs, content_id equal) does not reinstall. No automatic downgrade: if the installed semver is greater than the slot's, keep the install; Advanced may offer 'use catalog revision' with confirmation; hd-legacy (no semver) still updates on content_id difference. Pack removed from the catalog: keep install and per-ROM choice, no toast; still visible in Advanced. Reinstall preserves DisabledPacks and per-section flags (keyed by container name, unchanged on update). Sibling folder always wins: no catalog write, update or picker while present. .mep-install.json gains pack_id and content_id next to recipe_hash / source.sha256 / deps / installed_at. Slices: P.2 (CI) and P.6 (client) of the consolidated PRD, Part B.

## Consequences


## Alternatives

