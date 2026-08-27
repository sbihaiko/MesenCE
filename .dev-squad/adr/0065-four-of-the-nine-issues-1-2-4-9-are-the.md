# ADR-0065: Four of the nine issues (1, 2, 4, 9) are the same Mesen.sln question,...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0122

## Context
Raised during auditor-b: Four of the nine issues (1, 2, 4, 9) are the same Mesen.sln question, and treating that repetition as signal would misprioritize the list. The decision was in fact recorded, with rationale, consequences, and an explicit re-evaluation trigger, in `UI/AGENTS.md` (~lines 57-75): out of the .sln, unit-tests.yml calls the csproj directly, revisit by confirming the win-x64/AOT restore on Windows or by adding it with `Build.0` disabled under `Release|x64`. Issues 2 and 4's specific complaint — that the decision was written up in T5 after T1 had already authored the csproj — is process critique of an outcome that landed correctly anyway (the csproj is RID-less and reference-free as required). That part is noise. What survives is only issue 9's narrow, real point about placement, below. When several critics converge on one topic, check whether they are independent observations or one concern refracted; here it was the latter.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
