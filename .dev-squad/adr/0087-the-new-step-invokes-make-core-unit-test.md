# ADR-0087: The new step invokes `make core-unit-tests` with no make flags, so it...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during Execute/T1: The new step invokes `make core-unit-tests` with no make flags, so it silently inherits the makefile's `CXX := clang++` default (a `:=` assignment that overrides any environment CXX). By contrast .github/workflows/build.yml's Linux matrix deliberately exercises both toolchains (`USE_GCC=true` and the clang default, build.yml L69-71). The C++ unit-test harness is therefore gated on exactly one unpinned compiler, while the production core is gated on two - a divergence in toolchain coverage that is not recorded anywhere.

## Decision
Either state explicitly (in .github/AGENTS.md's unit-tests.yml contract) that core-unit-tests is intentionally clang-only for cheapness and that gcc coverage is build.yml's job, or add a small `USE_GCC=true`/default matrix to the core-unit-tests step so a gcc-only C++17 breakage in ChannelRoleClassifier/MepPack cannot land green.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
