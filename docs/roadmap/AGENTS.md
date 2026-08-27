# docs/roadmap/

## Purpose

Execution plans and the enhancement-ecosystem PRD. Status in the header is the
source of truth for whether a phase is still work.

## Ownership

Owned with `docs/` (see parent `docs/AGENTS.md`). Does not own specs, ADRs, or
runtime behavior.

## Local Contracts

- Header shape: `Status`, PRD/spec links, out-of-spec line — same as
  `plano-execucao-F3.md`.
- Product consoles on `main`: NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA.
  Plans must not assume SNES, PC Engine, WonderSwan, or ColecoVision cores,
  MSU-1, or Super Game Boy. SNES **gamepads** (`SnesController` and related
  port devices) stay as input for remaining cores. See `plano-reducao-cores.md`.
- Completed plans stay as the record of what shipped; if a later cut makes a
  path or foundation vanish, say so in one line and point here — do not leave
  "already supported" pointing at deleted trees.

## Work Guidance

- New plan: `plano-*.md` in this folder.
- Core reduction: `plano-reducao-cores.md` (completed).
- Host gamepad tester: `plano-host-input-tester.md`.
- Community pack → MEP conversion tooling (draft):
  `PRD-community-pack-mep-conversion.md`.

## Verification

Plans have no automated check. Specs used by a plan: `python3 scripts/validate-specs.py`.

## Child DOX Index
