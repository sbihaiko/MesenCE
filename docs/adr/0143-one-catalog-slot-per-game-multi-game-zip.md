# ADR-0143: one catalog slot per game; multi-game zips expand into sibling packs and issues

- Status: accepted
- Date: 2026-08-29
- Amends ADR-0140 source (2): pack_id = origin × game (one slot per game)

## Context
Product rule (user decision): there must be one pack per game and one issue per game. If a submitted zip contains more than one game pack, the pipeline MUST expand it into more than one pack and more than one issue. The contributor only opens a single issue; the automation performs the expansion. Root cause: ADR-0140 source (2) makes pack_id equal to owner/repo for all packs from one origin, and ADR-0141 keeps one live slot per pack_id, so the six liquidzgit/hdnes submissions (one game each) collapse to a single Duck Hunt slot. The fix must give each game its own pack_id (origin x game) and its own live slot, and must expand a multi-game zip into N packs + N sibling issues automatically.

## Decision
One live catalog slot per game: pack_id becomes origin x game (the declared MEP id when the pack declares one, else owner/repo x game-name, where the game is identified by targets[].name from pack.json when present, else the candidate subfolder name in a legacy HD pack). A submission whose zip contains N game packs is expanded by the pipeline into N packs with distinct pack_ids and N real sibling issues, created automatically via gh. The contributor opens exactly one issue. Sibling issues are linked: each mep-meta records a siblings[] field, the workflow posts a comment with the sibling links, and the issues carry the pack:split label. ADR-0141's one-slot-per-pack_id rule keeps operating per pack_id — it just becomes one slot per game because each game has its own pack_id.

## Consequences

Implementation state (verified 2026-09-01):
- `pack_id` = origin × game: `scripts/pack_id_rules.py:92-113` (`resolve_pack_id` appends `:<game-slug>` from the caller's `game` or mep-meta `game`, `game_slug` :71, `_meta_game` :83); shipped in `e831be33`, tests in `scripts/test_pack_id_rules.py`. Live rows: `liquidzgit/hdnes:ice-climber`, `pepcodes/hdnes-graphics-pac:pac-man-namco-us-1993`, `tastichacks/contra80s:contra-usa`, … (`docs/community-packs.json`).
- Multi-game detection: `scripts/mep_lint.py` recurses into nested game zips of a repo-link container (`57ddd599`, `scripts/test_mep_nested_zip.py`).
- Expansion into N packs + N sibling issues: `scripts/validate_pack_local.sh` (creates the siblings with `gh issue create … --label pack:split` :245, relabels the primary :256, writes mep-meta `game` and `siblings[]` :673-674, links them :703-735). The `pack:split` label is seeded by `scripts/ensure_community_pack_labels.sh:30`.
- ADR-0141's slot rule is untouched — it just runs per game because each game has its own `pack_id`.
- Eight of the nine LiQuiDz siblings this ADR produced were later de-listed by ADR-0148 (audio-only, off-catalog `.ogg`), so the slot expansion and the self-contained-row rule are independent.
Not implemented: the GitHub Actions workflow (`.github/workflows/community-pack-validate.yml`) does not perform the split — it neither records `game` nor `siblings[]` in mep-meta (its `resolve_pack_id` call at :1044 therefore yields the bare `owner/repo` for a GitHub URL without a declared `id`); today the expansion exists only in the local harness, so a fresh multi-game submission validated by CI alone still collapses to one slot per origin. Decision (2026-09-01): the split stays a manual step (`scripts/validate_pack_local.sh` run by the maintainer, siblings opened by hand) until the next multi-game submission arrives; automating it in the workflow is deferred, not rejected.

## Alternatives

- Keep ADR-0140 source (2) as bare `owner/repo` and ask contributors to publish one repo per game: rejected — the six liquidzgit/hdnes submissions (one game each, one repo) collapsed into a single Duck Hunt slot (Context).
- One issue per zip listing N games in one row: rejected — the product rule is one pack and one issue per game, so votes, hashes and verdicts stay per game.
- Ask the contributor to open N issues by hand: rejected — the contributor opens exactly one issue; the automation performs the expansion.
- Derive the game from the Issue Form title instead of the pack: rejected — the game identity comes from `targets[].name` in `pack.json`, else the candidate subfolder of a legacy HD pack (Decision), so it follows the artifact, not the submitter's text.
