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

- Planning: a single document, `docs/roadmap/PRD-mesence-enhancement-ecosystem.md`
  (vision, standards, shipped record, pending slices incl. the host gamepad
  tester and the console reduction). No separate `plano-*.md` files — see
  `docs/roadmap/AGENTS.md` for the contract. Earlier plans live in git history.
- `hd-pack-authoring.md` - human-facing guide for community HD/MEP pack
  submissions, linked from `.github/ISSUE_TEMPLATE/community-pack.yml`;
  summarizes the "Aceito (MEP completo)" vs. "Aceito parcial (HD Mesen)" vs.
  "Inválido" triage outcomes and cites `docs/specs/MEP-v1.md` §5.1/§5.2/§5.3/§6.

## Verification

- Specs: `python3 scripts/validate-specs.py` from the repo root.
- `hd-pack-authoring.md`: `./scripts/checks/verify_hd_pack_authoring_doc.sh`.
- Plans have no automated check.

## Child DOX Index

- specs/ — ESP, MEP, MEI, hires-gbsms drafts and `golden/`
- roadmap/ — the single consolidated PRD (product consoles: NES, GB, SMS-family, GBA)
