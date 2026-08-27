# docs/roadmap/

## Purpose

The fork's planning lives in **one** document,
`PRD-mesence-enhancement-ecosystem.md`: vision and legal principles, the
standards adopted/written, a one-line record of what shipped, and the
pending work sliced for dev-squad runs. The header `Status` and the slice
tables are the source of truth for whether something is still work.

## Ownership

Owned with `docs/` (see parent `docs/AGENTS.md`). Does not own specs
(`docs/specs/`), ADRs (`.dev-squad/adr/`), or runtime behavior.

## Local Contracts

- Single PRD. Do not create `plano-*.md` or a second PRD; add a slice table
  (or a row) to the existing document instead. When a slice ships, move it
  to §3 "What has shipped" as one line and delete its row — completed plans
  are not kept as prose here, git history is the record (decision of
  2026-08-27; the former `plano-execucao-F3/F5`, `plano-reducao-consoles`,
  `plano-host-input-tester` and the two earlier PRDs were consolidated and
  deleted that day).
- Product consoles on `main`: NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA. Plans
  must not assume SNES, PC Engine, WonderSwan, or ColecoVision cores, MSU-1,
  or Super Game Boy. SNES **gamepads** (`SnesController` and related port
  devices) stay as input for the remaining cores.
- Decisions are not made in the PRD: an architecture/trade-off choice goes
  through an ADR (`/dev-squad:adr`), and the PRD's §6 table points at it.
- One dev-squad run per slice; never feed a whole phase or the whole PRD to
  a single run.
- Prose is en-US (CLAUDE.md); quoted GitHub Project Status option names
  stay verbatim.

## Verification

Plans have no automated check. Specs used by a plan: `python3 scripts/validate-specs.py`.

## Child DOX Index
