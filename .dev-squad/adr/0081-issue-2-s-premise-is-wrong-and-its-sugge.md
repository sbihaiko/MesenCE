# ADR-0081: Issue 2's premise is wrong and its suggested fix would create the exa...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0124

## Context
Raised during auditor-b: Issue 2's premise is wrong and its suggested fix would create the exact divergence it warns about. (a) A consumer list IS already recorded — in the fixture's own header (`docs/specs/golden/mep/path-cases.txt:1-7`: "Shared zip-slip fixture (Fase 1 + Fase 4B) … Consumed today by UI.Tests/Mep/MepZipValidatorTests.cs … a later Fase 4B C++ suite reads this same file"). (b) The claimed third consumer is wrong: `scripts/validate-specs.py` never reads `path-cases.txt` — it validates `golden/mep/pack.json` only (line 128). Confirmed consumers of `path-cases.txt` are exactly two: `UI.Tests/Mep/MepZipValidatorTests.cs` and `scripts/core_unit_tests.cpp`. Adding a second consumer list to `docs/AGENTS.md` would put the same list in two files that must then be kept in sync — the multi-reader drift the issue is about. The real (small) residual: the header's tense is now stale ("a later Fase 4B C++ suite" describes shipped code) and it predates the C++ consumer. Fix in place — one-line header edit naming both current readers — and do NOT open a new doc. `pack.json` is the fixture that genuinely has three readers (validate-specs.py, core_unit_tests.cpp, docs/specs/MEP-v1.md as the documented example); if any fixture warrants a consumer note it is that one.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
