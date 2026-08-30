# docs/roadmap/

## Purpose

The fork's planning lives in one consolidated PRD under this folder:

- `PRD-mesence-enhancement-ecosystem.md` — the single roadmap, organised
  as two Parts. Part A is the pack/core roadmap (vision, legal principles,
  standards, shipped record, Phase 5/6 slices, input tester, Phase 8
  border layer). Part B is the default-GUI roadmap (player chrome,
  Advanced GUI, `pack_id`/`content_id`/version, duplicates, picker,
  quick-enhancements panel). Each Part carries its own header `Status`,
  slice table, and ADR map, which are the source of truth for that
  surface.

This is the 2026-08-30 unification of the former two PRDs
(`PRD-mesence-enhancement-ecosystem.md` and `PRD-player-shell.md`) into a
single file with two Parts. Each Part keeps its own internal `§N`
numbering verbatim, so a `§N` reference resolves within the Part that
uses it.

Do not revive `plano-*.md` or the 2026-08-27 deleted PRDs. Do not split
this file back into multiple PRDs; a new product surface is a phase in
one of the two Parts.

## Ownership

Owned with `docs/` (see parent `docs/AGENTS.md`). Does not own specs
(`docs/specs/`), ADRs (`.dev-squad/adr/`), or runtime behavior.

## Local Contracts

- One consolidated PRD, no `plano-*.md`. Pack/core slices go in Part A;
  player-shell slices go in Part B. When a slice ships, move it to its
  Part's shipped record as one line and delete its row — completed plans
  are not kept as prose here, git history is the record. The 2026-08-27
  consolidation (deleted `plano-execucao-F3/F5`, `plano-reducao-consoles`,
  `plano-host-input-tester`, and the two earlier ecosystem PRDs) still
  stands; the player-shell surface was added on 2026-08-28 and merged
  into this single file as Part B on 2026-08-30, not revived as a
  separate file.
- Product consoles on `main`: NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA. Plans
  must not assume SNES, PC Engine, WonderSwan, or ColecoVision cores, MSU-1,
  or Super Game Boy. SNES **gamepads** (`SnesController` and related port
  devices) stay as input for the remaining cores.
- Decisions are not made in a PRD: an architecture/trade-off choice goes
  through an ADR (`/dev-squad:adr`), and the relevant Part's ADR map
  points at it.
- One dev-squad run per slice; never feed a whole phase or the whole PRD to
  a single run.
- Prose is en-US (CLAUDE.md); quoted GitHub Project Status option names
  stay verbatim.

## Verification

Plans have no automated check. Specs used by a plan: `python3 scripts/validate-specs.py`.

## Child DOX Index
