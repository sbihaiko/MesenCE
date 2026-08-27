# ADR-0089: Issue 3's factual premise is wrong and its suggested remedy should be...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0131

## Context
Raised during auditor-b: Issue 3's factual premise is wrong and its suggested remedy should be rejected. Makefile:159 defines `CORESRC := $(shell find Core -name '*.cpp')`, so `Core/Shared/Audio/ChannelRoleClassifier.cpp` and `Core/Shared/EnhancementPacks/MepPack.cpp` are already compiled by build.yml's linux matrix under `USE_GCC=true` on both x64 and arm64 — a gcc-only C++17 breakage in those two files cannot land green today. The only file gated exclusively on clang is the harness itself, `scripts/core_unit_tests.cpp`, and the `core-unit-tests` recipe passes `-w`, so warning-level toolchain divergence is muted and only hard compile errors matter. Adding a `USE_GCC` matrix to the step would double the cost of the cheap lane to gate one test-only file. Take the issue's first branch only: one line in .github/AGENTS.md's unit-tests.yml contract saying core-unit-tests is intentionally clang-only for cheapness and that gcc/arm coverage of the Core sources is build.yml's job.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
