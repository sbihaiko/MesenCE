# ADR-0161: CONFIRMED but MINOR and mechanical (issue 3). UI/UI.csproj:616 embeds...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during auditor-b: CONFIRMED but MINOR and mechanical (issue 3). UI/UI.csproj:616 embeds `Include="../scripts/pack_host_allowlist.json"`, the only EmbeddedResource in the file pointing outside the project cone. `Link="Resources\pack_host_allowlist.json"` is the standard fix. One trap the critic missed: `scripts/checks/verify_pack_host_allowlist_embed.sh:19` asserts the literal string `Include="../scripts/pack_host_allowlist.json"`, so adding Link without updating that check to the full triple breaks doc-checks. Do both in one commit or not at all.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
