# docs/

## Purpose

Durable documentation for this fork: open specs, execution plans, and the enhancement-ecosystem narrative. Not source of truth for runtime behavior — the code and ADRs win if they diverge.

## Ownership

Owns `docs/specs/` (CC0), `docs/roadmap/` (execution plans and the PRD), `docs/media/`, and top-level ecosystem notes. Does not own `AGENTS.md` files in other trees, Core/UI source, or `.dev-squad/adr/`.

## Local Contracts

- Specs under `specs/` stay CC0 and RFC 2119; breaking change = major semver bump of that spec.
- Roadmap plans record status in the header and do not duplicate ADRs.
- No derivative game content except the short `media/` demo excerpts already allowed by `CONTRIBUTING.md`.

## Work Guidance

- New execution plan: `docs/roadmap/plano-*.md`, same header shape as `plano-execucao-F3.md` (`Status`, links to PRD/spec).
- Unit-test refactor plan: completed (Fases 0-4) and removed; see git history for `docs/roadmap/plano-testes-unitarios.md`.

## Verification

- Specs: `python3 scripts/validate-specs.py` from the repo root.
- Plans have no automated check.

## Child DOX Index

- specs/ — ESP, MEP, MEI, hires-gbsms drafts and `golden/`
- roadmap/ — PRD and phase / refactoring plans
