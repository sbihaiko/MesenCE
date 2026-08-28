# docs/roadmap/

## Purpose

The fork's planning lives in two PRDs under this folder:

- `PRD-mesence-enhancement-ecosystem.md` — pack/core roadmap (vision, legal
  principles, standards, shipped record, Phase 5/6 slices, input tester).
  Its header `Status` and slice tables are the source of truth for that
  work. It indexes Phase 7 to the player-shell PRD; it does not duplicate
  chrome or pack-identity prose.
- `PRD-player-shell.md` — default GUI (player chrome, Advanced GUI,
  `pack_id`/`content_id`/version, duplicates, picker). Its own header
  `Status` and slice table (P.0–P.6) are the source of truth for that
  surface.

Do not revive `plano-*.md` or the 2026-08-27 deleted PRDs. Do not add a
third PRD; a new product surface is a phase in one of these two.

## Ownership

Owned with `docs/` (see parent `docs/AGENTS.md`). Does not own specs
(`docs/specs/`), ADRs (`.dev-squad/adr/`), or runtime behavior.

## Local Contracts

- Two PRDs, no `plano-*.md`. Pack/core slices go in
  `PRD-mesence-enhancement-ecosystem.md`; player-shell slices go in
  `PRD-player-shell.md`. When a slice ships, move it to that PRD's shipped
  record as one line and delete its row — completed plans are not kept as
  prose here, git history is the record. The 2026-08-27 consolidation
  (deleted `plano-execucao-F3/F5`, `plano-reducao-consoles`,
  `plano-host-input-tester`, and the two earlier ecosystem PRDs) still
  stands; the player-shell PRD is an added surface (2026-08-28), not a
  revival of those files.
- Product consoles on `main`: NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA. Plans
  must not assume SNES, PC Engine, WonderSwan, or ColecoVision cores, MSU-1,
  or Super Game Boy. SNES **gamepads** (`SnesController` and related port
  devices) stay as input for the remaining cores.
- Decisions are not made in a PRD: an architecture/trade-off choice goes
  through an ADR (`/dev-squad:adr`), and that PRD's ADR map points at it.
- One dev-squad run per slice; never feed a whole phase or the whole PRD to
  a single run.
- Prose is en-US (CLAUDE.md); quoted GitHub Project Status option names
  stay verbatim.

## Verification

Plans have no automated check. Specs used by a plan: `python3 scripts/validate-specs.py`.

## Child DOX Index
