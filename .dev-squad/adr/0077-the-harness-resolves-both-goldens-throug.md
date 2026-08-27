# ADR-0077: The harness resolves both goldens through cwd-relative literals ("doc...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0129

## Context
Raised during Execute/T1: The harness resolves both goldens through cwd-relative literals ("docs/specs/golden/mep/path-cases.txt", "docs/specs/golden/mep/pack.json"), so Bloco B only works when the binary is launched from the repo root. Invoked from anywhere else (IDE run configuration, a CI step with a different working directory, or a developer running ./scripts/core_unit_tests from scripts/) the two fixture cases register FAIL and the binary exits 1 for an environmental reason rather than a real regression. The failure is at least loud and self-explaining ('run from repo root'), and `make core-unit-tests` always satisfies the precondition, so this is a contract choice rather than a bug.

## Decision
Make the golden root overridable - a MESEN_GOLDEN_ROOT (or argv[1]) prefix defaulting to the current relative paths - or pass the repo root into the binary from the makefile recipe, so the harness's only hard requirement is documented in one place instead of implied by cwd.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
