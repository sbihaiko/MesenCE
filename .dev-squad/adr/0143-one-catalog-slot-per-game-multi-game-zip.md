# ADR-0143: one catalog slot per game; multi-game zips expand into sibling packs and issues

- Status: accepted
- Date: 2026-08-29

## Context
Product rule (user decision): there must be one pack per game and one issue per game. If a submitted zip contains more than one game pack, the pipeline MUST expand it into more than one pack and more than one issue. The contributor only opens a single issue; the automation performs the expansion. Root cause: ADR-0140 source (2) makes pack_id equal to owner/repo for all packs from one origin, and ADR-0141 keeps one live slot per pack_id, so the six liquidzgit/hdnes submissions (one game each) collapse to a single Duck Hunt slot. The fix must give each game its own pack_id (origin x game) and its own live slot, and must expand a multi-game zip into N packs + N sibling issues automatically.

## Decision
One live catalog slot per game: pack_id becomes origin x game (the declared MEP id when the pack declares one, else owner/repo x game-name, where the game is identified by targets[].name from pack.json when present, else the candidate subfolder name in a legacy HD pack). A submission whose zip contains N game packs is expanded by the pipeline into N packs with distinct pack_ids and N real sibling issues, created automatically via gh. The contributor opens exactly one issue. Sibling issues are linked: each mep-meta records a siblings[] field, the workflow posts a comment with the sibling links, and the issues carry the pack:split label. ADR-0141's one-slot-per-pack_id rule keeps operating per pack_id — it just becomes one slot per game because each game has its own pack_id.

## Consequences


## Alternatives

