# ADR-0111: The edited scripts/AGENTS.md bullet places `check-f5-4b-doc.sh` in th...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during Execute/T3: The edited scripts/AGENTS.md bullet places `check-f5-4b-doc.sh` in the list described as "repo-hygiene shell checks run from `make` or CI", but the script is wired into neither (grep over makefile and .github/workflows finds only `check-core-manifest.sh`). The same is already true of `check-file-loc.sh`, `verify-fase0-1-dox.sh` and `verify-ui-logic-firewall.sh`, so this is a pre-existing pattern rather than a new inaccuracy — but a doc guardrail nobody runs will not actually protect the header contract it was written for.

## Decision
Either add a `make doc-checks` (or CI step) that runs the four unwired hygiene scripts, or reword the bullet so it does not claim they run from make/CI.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
