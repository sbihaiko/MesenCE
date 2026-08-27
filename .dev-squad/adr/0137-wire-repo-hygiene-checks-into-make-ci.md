# ADR-0137: Wire repo-hygiene shell checks into make/CI or stop claiming they run

- Status: accepted (2026-08-27; decision = items 1–4 below, work requested as slice H1 of `docs/roadmap/PRD-mesence-enhancement-ecosystem.md`. Item 3's "make the doc true" half already landed the same day: `scripts/AGENTS.md` now says only `check-core-manifest.sh` is wired. `check-f5-4b-doc.sh` was deleted on 2026-08-27 with the plan header it guarded, so the target wires three scripts plus `check-file-loc.sh`, not four)
- Date: 2026-08-27
- Consolidates: ADR-0111, ADR-0118, ADR-0092 (rejected — premise false, target scripts never shipped)
- Related: ADR-0132 (the `check-f5-4b-doc.sh` guardrail was added by the F5.4b run and later deleted)

## Context

`scripts/AGENTS.md:106-108` describes `check-core-manifest.sh`,
`check-file-loc.sh`, `verify-fase0-1-dox.sh`, `verify-ui-logic-firewall.sh` and
`check-f5-4b-doc.sh` as "repo-hygiene shell checks run from `make` or CI".
Only one of them is: `makefile:214-215` defines `check-manifest:` running
`./scripts/check-core-manifest.sh`, and the `ui` and `core` targets depend on
it (`makefile:217`, `:226`). No `.github/workflows/*.yml` invokes any of the
five. Four of five never execute anywhere except by hand (ADR-0111, ADR-0118).

This is pre-existing rot, but the F5.4b run compounded it: it added a fifth
unwired script (`check-f5-4b-doc.sh`, guarding the F5.4b clause in
`docs/roadmap/plano-execucao-F5.md`'s header Status line) together with a doc
claim that it runs. A documented-but-unrun guardrail is worse than none,
because reviewers trust it.

ADR-0092 (from the never-executed F5 closeout run `d662e62e2648`) claimed that
no `scripts/*.py` carries the executable bit and that the planned
`scripts/mep_build.py`/`test_mep_build.py` would be the first to need
`chmod +x`. Both halves are false at HEAD: those scripts do not exist, and the
convention is already mixed — `gen_mep_fallback_test_pack.py`,
`generate_community_pack_catalog.py`, `test_mep_compare_auto_palettes.py` and
`validate_palette_variants.py` are `+x` with a `#!/usr/bin/env python3`
shebang while the other eleven `.py` files are not. ADR-0092 is therefore
rejected; the only surviving point is a one-line convention (below).

## Decision

1. **Wire the checks.** Add a `make doc-checks` target that runs, in order,
   `verify-fase0-1-dox.sh` and `verify-ui-logic-firewall.sh` (and
   `check-f5-4b-doc.sh` while it existed — deleted 2026-08-27), failing on
   the first non-zero exit. `check-file-loc.sh`
   takes `<file> <max-lines>` arguments and encodes no list of its own, so
   `doc-checks` must call it once per guarded file with the cap the owning
   doc states (e.g. the 200-line cap on `Core/Shared/Audio/MidiExporter.cpp`
   its header names); a guardrail with no caller and no argument list is not a
   guardrail. `check-manifest` stays as is and `doc-checks` depends on it.
2. **Run it in CI.** Every workflow that builds the core or the UI runs
   `make doc-checks` before the build step, so a broken doc/header contract
   fails the PR rather than a later human read. The checks are pure shell and
   need no toolchain, so they can run on the cheapest runner first.
3. **Make the doc true.** Reword `scripts/AGENTS.md:106-108` to name the
   target (`make doc-checks`, also invoked by CI) and to state that any new
   `check-*.sh`/`verify-*.sh` must be added to that target in the same commit
   — otherwise it does not get the "repo-hygiene check" label.
4. **Python exec-bit convention (from ADR-0092, reduced to one sentence).**
   Scripts are documented and invoked as `python3 scripts/<name>.py`; a
   shebang plus `+x` is allowed but never required, and acceptance criteria
   must not test for the executable bit.

If (1)–(2) are not wanted, the minimum acceptable alternative is (3) alone,
reworded to say the scripts are manual and listing which command runs each.

## Consequences

- The remaining checks become real gates (the F5.4b header guardrail is
  gone with the plan file it guarded; ADR-0132's "repoint ADR-0050 step b"
  follow-up is now moot for that script).
- A few seconds added to `make ui`/`make core` (shell only).
- `check-file-loc.sh` gains an explicit list of guarded files in the makefile,
  which is where the per-file caps stop being folklore.
- Future dev-squad runs that add a hygiene script have a concrete wiring step
  to verify in their acceptance criteria, instead of a prose claim.

## Alternatives

- **Reword only** (`scripts/AGENTS.md` says "manual checks") — honest and
  zero-cost, but leaves the guardrails unrun; acceptable fallback, not
  preferred.
- **CI only, no make target** — rejected: developers would have no local
  equivalent, and the makefile already hosts `check-manifest`.
- **Fold the checks into `scripts/checks/`** (per-AC verifiers) — rejected:
  those are one-script-one-AC, invoked by the AC's Verification command, not
  repo-wide gates.
- **Adopt shebang + `chmod +x` repo-wide** (ADR-0092's second option) —
  rejected: churn on fifteen files for no functional gain; `python3 scripts/…`
  is what every doc already says.
