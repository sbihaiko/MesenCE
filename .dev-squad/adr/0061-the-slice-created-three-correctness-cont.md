# ADR-0061: The slice created three correctness contracts and mechanically enforc...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0123

## Context
Raised during auditor-b: The slice created three correctness contracts and mechanically enforced none of them — this is the run's real structural debt, and issues 3, 5, and 4/9 are three symptoms of it rather than three problems. Verified: (a) `scripts/verify-ui-logic-firewall.sh` exists and works, but `grep -rn verify-ui-logic-firewall` across the repo hits only `UI/AGENTS.md:91` and the dev-squad spec — it is wired into neither the makefile (whose only new target is `unit-tests`, running `dotnet test` alone) nor any of the five workflows; (b) `scripts/validate-specs.py` validates golden files by four explicit calls at lines 127-130 (esp/mep/mei/hires-gbsms) and `path-cases.txt` is not among them, so its `path<TAB>ok|bad` format is unchecked; (c) with `UI.Tests` out of `Mesen.sln`, `dotnet-format-check.yml`'s root-level `dotnet format --verify-no-changes` resolves to the .sln and never sees `UI.Tests/**` or the test-side compile of `UI/Logic/**`. Each guardrail is a documented convention, and a convention that no command runs decays at the first contributor who does not read the AGENTS.md. The fix is cheap and shared: one `make verify` / CI step that runs the firewall script plus a `path-cases.txt` format check appended to validate-specs.py.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
