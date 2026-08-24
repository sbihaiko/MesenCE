# ADR-0007: Guard against Core source-manifest drift between the makefile glob and Core.vcxproj

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: The project maintains two independent source manifests — a globbing makefile and a hand-enumerated Core.vcxproj (308 explicit entries). Any work that adds Core sources builds green on macOS/Linux while the MSVC project silently drifts, and the current effort adds six new Core sources across three parallel tasks.

## Decision
Either add a CI/check script that diffs `find Core -name '*.cpp'` against Core.vcxproj's ClCompile entries and fails on drift, or convert Core.vcxproj to wildcard includes so the two manifests cannot diverge.

## Consequences
Windows builds stop rotting silently as squad tasks add Core sources; the check also protects every future task, not just this run.

## Alternatives
Rely on task briefs reminding actors to touch Core.vcxproj: has already proven unreliable (the manifests have drifted before) and does not survive parallel tasks.
