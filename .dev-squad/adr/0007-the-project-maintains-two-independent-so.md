# ADR-0007: The project maintains two independent source manifests — a globbing m...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: The project maintains two independent source manifests — a globbing makefile and a hand-enumerated Core.vcxproj (308 explicit entries). Any work that adds Core sources builds green on macOS/Linux while the MSVC project silently drifts, and this task adds six new Core sources across three parallel tasks.

## Decision
Either add a CI/check script that diffs `find Core -name '*.cpp'` against Core.vcxproj's ClCompile entries and fails on drift, or convert Core.vcxproj to wildcard includes so the two manifests cannot diverge.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
