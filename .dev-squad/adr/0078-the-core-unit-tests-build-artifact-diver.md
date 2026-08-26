# ADR-0078: The `core_unit_tests` build artifact diverges from the pattern its th...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during Execute/T2: The `core_unit_tests` build artifact diverges from the pattern its three sibling harness binaries follow. `.gitignore` lists `scripts/headless_record`, `scripts/spike_sound_driver`, and `scripts/roles_probe` by name but has no entry for `scripts/core_unit_tests`. Rather than closing that gap, scripts/AGENTS.md elevates a manual workaround into a durable Local Contract: after `make core-unit-tests` the binary 'shows as untracked in git status and must be excluded by hand (or removed with rm -f scripts/core_unit_tests) before staging.' Documenting the gap honestly is better than the doc lying about it (c9d11911 fixed exactly that false claim), but a contract that depends on every future agent remembering a hand-exclusion step is weaker than the one-line mechanism its peers already use — and a `make core-unit-tests` run immediately before a `git add -A` will commit a ~200KB binary. I confirmed the divergence is deliberate, not an oversight: commit 2fdd41a2 'fix(scope): drop unrelated memory-metrics commit and .gitignore edit from T1 branch' removed the .gitignore edit for scope reasons, so this is a scope trade-off worth a human decision rather than a defect. .gitignore is not in T2's declared file list, so it is out of scope to fix here.

## Decision
Add `scripts/core_unit_tests` to .gitignore alongside its three siblings in a small follow-up task, then simplify the scripts/AGENTS.md Local Contracts bullet to just 'compiled binaries are build output, never git add them - all four are listed in the root .gitignore', deleting the hand-exclusion workaround.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
