# ADR-0144: The allow-list is embedded via a path outside the project cone (`../s...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during decompose: The allow-list is embedded via a path outside the project cone (`../scripts/pack_host_allowlist.json`), unlike every existing EmbeddedResource in the file, which uses in-project backslash paths. It works because LogicalName is explicit, but it makes UI.csproj depend on the repo layout above itself, which is fragile for any packaging that builds UI/ in isolation.

## Decision
Keep scripts/pack_host_allowlist.json as the single source of truth but declare the item with an explicit Link (e.g. Link="Resources\pack_host_allowlist.json") alongside the LogicalName, and have verify_pack_host_allowlist_embed.sh assert the full triple so the intent is pinned.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
