# ADR-0085: The spec (following ADR-0079's ban on a new job) adds the C++ core-un...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0126

## Context
Raised during spec: The spec (following ADR-0079's ban on a new job) adds the C++ core-unit-tests build+run as a second step inside the same 'ui-tests' job that runs 'dotnet test'. This couples two unrelated toolchains (dotnet + C++ compiler) and two unrelated test suites into one job/one pass-fail signal: a C++ compile failure on ubuntu-latest (the exact risk ADR-0079 flags as unverified) would report as a generic 'ui-tests' failure, making it harder for a future contributor to tell at a glance whether the C# or the C++ suite broke, and forces anyone iterating on just the C# tests to also pay for/wait on the C++ compile in the same job run.

## Decision
Non-blocking for this task, but worth a human decision later: consider a second job (or a matrix step with a distinct 'name:') in the same workflow file so CI status clearly attributes failure to the C++ harness vs. the C# tests, without violating the 'no new workflow file' boundary already set.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
