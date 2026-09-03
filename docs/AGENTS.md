# docs/

## Purpose

Durable documentation for this fork: open specs, execution plans, and the enhancement-ecosystem narrative. Not source of truth for runtime behavior — the code and ADRs win if they diverge.

## Ownership

Owns `docs/specs/` (CC0), `docs/roadmap/` (the consolidated PRD), `docs/adr/` (the decision register, moved here from `.dev-squad/adr/` on 2026-09-03), `docs/media/`, and top-level ecosystem notes. Does not own `AGENTS.md` files in other trees or Core/UI source.

## Local Contracts

- Specs under `specs/` stay CC0 and RFC 2119; breaking change = major semver bump of that spec.
- `adr/` is a different contract from `specs/`: not CC0, not RFC 2119, ids never reused (ADR-0035), three statuses only (`proposed`/`accepted`/`superseded`). Write one with the `adr` skill; see CLAUDE.md for the binding rules.
- Roadmap plans record status in the header and do not duplicate ADRs.
- No derivative game content except the short `media/` demo excerpts already allowed by `CONTRIBUTING.md`.

## Work Guidance

- Planning: `docs/roadmap/PRD-mesence-enhancement-ecosystem.md` — one
  consolidated PRD, two Parts: Part A (pack/core roadmap) and Part B (default
  GUI, pack identity, picker). No `plano-*.md`. See `docs/roadmap/AGENTS.md`
  for the contract.
- `community-pack-intake-handoff.md` — agent brief to submit researched
  HD/MEP packs through the Issue Form pipeline (allow-listed ZIP only;
  do not hand-edit pack rows into the generated catalog). Extra ROM
  hashes for auto-install belong in `scripts/rom_target.py`;
  `community-packs.json`'s `rom.sha1`/`rom.sha1s` must match that map.
  Not a player-facing guide.
- `hd-pack-authoring.md` - human-facing guide for community HD/MEP pack
  submissions, linked from `.github/ISSUE_TEMPLATE/community-pack.yml`;
  summarizes the "Aceito (MEP completo)" vs. "Aceito parcial (HD Mesen)" vs.
  "Inválido" triage outcomes and cites `docs/specs/MEP-v1.md` §5.1/§5.2/§5.3/§6.
  Also documents the split-distribution/MEP Recipe flow (ADR-0138 §12):
  the `external_assets`/`external_assets_license` form fields and the
  `assets:external` label, citing `docs/specs/MEP-recipe-v1.md`.

## Verification

- Specs: `python3 scripts/validate-specs.py` from the repo root.
- ADRs: `python3 scripts/checks/verify_adr_refs.py` (also in `make doc-checks`) — every cited `ADR-NNNN` resolves to a file.
- `hd-pack-authoring.md`: `./scripts/checks/verify_hd_pack_authoring_doc.sh`.
- Plans have no automated check.

## Child DOX Index

- adr/ — the decision register (`NNNN-<kebab-title>.md`); accepted ADRs are binding
- specs/ — ESP, MEP, MEI, MEP-recipe, hires-gbsms drafts and `golden/`
- roadmap/ — consolidated PRD (Part A: pack/core; Part B: player shell) (product consoles: NES, GB, SMS-family, GBA)
