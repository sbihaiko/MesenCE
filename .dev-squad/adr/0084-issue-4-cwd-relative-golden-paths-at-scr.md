# ADR-0084: Issue 4 (cwd-relative golden paths at `scripts/core_unit_tests.cpp:11...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0129

## Context
Raised during auditor-b: Issue 4 (cwd-relative golden paths at `scripts/core_unit_tests.cpp:116,144`) is a genuine observation and its own self-assessment is right: it is a contract choice, not a defect. The precondition is documented at the top of the file (line 6, "Run from the repo root so the golden paths resolve"), the failure is loud and self-explaining, and `make core-unit-tests` satisfies it by construction. Lowest priority of the five, and the suggested `MESEN_GOLDEN_ROOT` env-var indirection should be resisted for now — it adds a configuration surface with zero current consumer, and it is exactly the kind of knob that later needs its own doc bullet and its own drift. Note the coupling with the CI item: GitHub Actions steps default to the checkout root, so wiring `make core-unit-tests` into `unit-tests.yml` does not create the failure mode described. Revisit only if a real second invocation site appears (an IDE run configuration, or a CI step that sets `working-directory`), and prefer passing the root from the makefile recipe over an env var if so.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
