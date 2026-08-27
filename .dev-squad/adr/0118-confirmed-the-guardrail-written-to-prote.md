# ADR-0118: Confirmed: the guardrail written to protect this run's own deliverabl...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during auditor-b: Confirmed: the guardrail written to protect this run's own deliverable is wired to nothing. scripts/AGENTS.md:60-63 lists check-core-manifest.sh, check-file-loc.sh, verify-fase0-1-dox.sh, verify-ui-logic-firewall.sh and the new check-f5-4b-doc.sh as 'repo-hygiene shell checks run from make or CI', but grep over makefile and .github/workflows finds only check-core-manifest.sh (makefile:215). Four of five never execute. This is pre-existing rot rather than a new regression, which is exactly why it warrants attention now: the run just added a fifth unwired script and a doc claim that it runs, so the drift is compounding. Either add a `make doc-checks` target wiring all four, or reword the bullet — a documented-but-unrun guardrail is worse than none, because reviewers trust it.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
