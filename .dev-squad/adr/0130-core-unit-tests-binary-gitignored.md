# ADR-0130: core_unit_tests binary is gitignored like its sibling harnesses

- Status: accepted (record of fact — `.gitignore` and `scripts/AGENTS.md` already reflect it; restored 2026-09-01 from b0b334b0^ after accidental deletion)
- Date: 2026-08-27
- Consolidates: ADR-0078, ADR-0082, ADR-0083

## Context
`make core-unit-tests` writes the compiled harness to `scripts/core_unit_tests`
(about 200 KB). Its three sibling harness binaries — `scripts/headless_record`,
`scripts/spike_sound_driver`, `scripts/roles_probe` — were already listed by
name in the root `.gitignore`. When Phase 4's T1 landed, its `.gitignore` edit
was dropped for scope reasons (commit 2fdd41a2, "drop unrelated memory-metrics
commit and .gitignore edit from T1 branch"), and `scripts/AGENTS.md` then
documented the gap as a Local Contract requiring a hand-exclusion or
`rm -f scripts/core_unit_tests` before staging (commit c9d11911 had previously
fixed a doc that falsely claimed the entry existed). ADR-0078/0082 flagged that
a documented manual step had replaced the one-line mechanism its peers use, so
a `make core-unit-tests` immediately before `git add -A` would commit a binary.

State at HEAD: `.gitignore:205-208` lists all four binaries
(`scripts/headless_record`, `scripts/spike_sound_driver`, `scripts/roles_probe`,
`scripts/core_unit_tests`), and `scripts/AGENTS.md:26-29` reads "Compiled
binaries (`core_unit_tests`, `roles_probe`, `headless_record`,
`spike_sound_driver`) are build output, not source - never `git add` them.
`.gitignore` at the repo root lists all four by name, so none of them show as
untracked after building." The hand-exclusion workaround is gone.

## Decision
Every harness binary produced by a makefile target under `scripts/` is listed
by name in the root `.gitignore`; `scripts/core_unit_tests` is included
alongside its three siblings. `scripts/AGENTS.md` states only the rule
("build output, never `git add`; all listed in `.gitignore`") and carries no
manual exclusion procedure. A new harness target must add its output binary to
`.gitignore` in the same commit that adds the target.

## Consequences
- `git status` stays clean after `make core-unit-tests`; no accidental binary
  commits.
- `scripts/AGENTS.md` Local Contracts describe a mechanism, not a chore.
- Process takeaway from ADR-0083 (recorded here as a consequence, not a rule):
  when a scope decision drops an adjacent edit, the closeout must queue it as
  tracked follow-up work rather than letting "documented honestly" become the
  terminal state. In this instance the follow-up was done.

## Alternatives
- Keep the hand-exclusion bullet in `scripts/AGENTS.md` (state after
  2fdd41a2/c9d11911): rejected — correctness depended on every future agent
  reading and remembering a doc bullet.
- Use a `scripts/.gitignore` or a pattern (e.g. ignore all extension-less
  files under `scripts/`): rejected — the repo convention is explicit
  per-binary entries in the root `.gitignore`, and a pattern would risk hiding
  real extension-less scripts.
- Emit the binary into an already-ignored build directory instead: rejected —
  the sibling harnesses all live in `scripts/`, and consistency was the point.
