# ADR-0082: Issue 5 is real, correctly diagnosed, and the cheapest fix in the set...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during auditor-b: Issue 5 is real, correctly diagnosed, and the cheapest fix in the set — act on it. Confirmed: `.gitignore:205-207` lists `scripts/headless_record`, `scripts/spike_sound_driver`, `scripts/roles_probe` and has no `scripts/core_unit_tests` entry, while `scripts/AGENTS.md:26-32` encodes the omission as a durable Local Contract requiring a hand-exclusion or `rm -f` before staging. The structural smell is precise: a documented manual step was substituted for a one-line mechanism that three sibling binaries already use, so correctness now depends on every future agent reading and remembering a doc bullet — and a `make core-unit-tests` immediately before `git add -A` commits a ~200KB binary. The scope call in 2fdd41a2 (dropping the .gitignore edit from T1's branch) was right on its own terms; the defect is that dropping it produced a documented workaround instead of a queued follow-up. Fix: add the one `.gitignore` line, then collapse the AGENTS.md bullet to "compiled binaries are build output, never `git add` them — all four are listed in the root `.gitignore`."

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
