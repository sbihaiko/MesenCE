# ADR-0153: The container-name derivation (submitter-influenced entry.Name -> fil...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during Execute/T2: The container-name derivation (submitter-influenced entry.Name -> filesystem folder name -> DisabledPacks key) is now implemented here, in a host-aware Services class, while every other identity/decision rule for community packs lives host-free in UI/Logic/Community*.cs where UI.Tests can exercise it. The sanitization is the security-critical part of this file (it feeds Directory.Delete(recursive) and the native extraction target) yet it is the one part with no test reachability, and a future second call site (the pack list UI, the DisabledPacks toggle) would have to duplicate or re-derive the same rule.

## Decision
Extract the pure name-sanitization + rooted-path assertion into a host-free UI/Logic/CommunityPackContainerName.cs so it dual-compiles into UI.Tests and becomes the single source of truth for the DisabledPacks key, leaving ResolveOutFolder in Services as the thin ConfigManager-aware wrapper.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
