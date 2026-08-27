# ADR-0129: core_unit_tests resolves goldens cwd-relative from the repo root; no env-var knob

- Status: accepted (record of fact — current behaviour, deliberately kept)
- Date: 2026-08-27
- Consolidates: ADR-0077 (rejected), ADR-0084

## Context
`scripts/core_unit_tests.cpp` reads two golden fixtures through cwd-relative
literals: `"docs/specs/golden/mep/path-cases.txt"` (line 126, Bloco B path
normalization) and `"docs/specs/golden/mep/pack.json"` (line 154,
`MepPack::Parse`). The file header (line 11) states the precondition: "Run
from the repo root so the golden paths resolve." Launched from any other
directory, the two fixture cases print FAIL and the binary exits non-zero for
an environmental reason.

ADR-0077 proposed making the golden root overridable (a `MESEN_GOLDEN_ROOT`
env var or `argv[1]`, or passing the root from the makefile recipe). ADR-0084
assessed this as a contract choice, not a defect: the precondition is
documented in the file, the failure is loud and self-explaining,
`make core-unit-tests` (`makefile:233`) satisfies it by construction because
make runs recipes from the repo root, and GitHub Actions steps default to the
checkout root, so the `Run core unit tests` step in
`.github/workflows/unit-tests.yml` (ADR-0126) does not hit the failure mode
either. There is zero second invocation site today.

## Decision
Keep the cwd-relative literals. The harness's only hard requirement is "run
from the repo root", documented in the file header and satisfied by the two
sanctioned entry points (`make core-unit-tests` locally and in CI). Do not add
a `MESEN_GOLDEN_ROOT` environment variable, an `argv[1]` root, or any other
configuration surface for the golden location.

Revisit only when a real second invocation site appears (an IDE run
configuration, or a CI step that sets `working-directory`). If that happens,
prefer passing the root as an argument from the makefile recipe over an
environment variable, so the knob stays in one place.

## Consequences
- No configuration surface to document, test, or keep from drifting; the
  header comment is the whole contract.
- Running `./scripts/core_unit_tests` from `scripts/` fails two cases with an
  explicit path message; this is accepted developer friction.
- Adding a third golden fixture follows the same literal pattern.

## Alternatives
- `MESEN_GOLDEN_ROOT` env var defaulting to the current relative paths
  (ADR-0077): rejected — adds a knob with zero consumers that later needs its
  own doc bullet and its own drift.
- `argv[1]` root passed by the makefile recipe (ADR-0077 variant): rejected
  for now; kept as the preferred shape if a second invocation site ever
  justifies a knob.
- Resolve paths relative to the executable's location: rejected — the binary
  lives in `scripts/`, is gitignored (ADR-0130), and coupling fixture lookup to
  binary placement is more fragile than the cwd contract.
