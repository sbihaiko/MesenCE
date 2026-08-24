# ADR-0005: MEP introduces a second, parallel enhancement-content system alongsid...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: MEP introduces a second, parallel enhancement-content system alongside the existing hires.txt HD Pack stack (HdPackLoader/HdNesPack/HdPackBuilder), and the spec defines no relationship between them: if a game has both an installed MEP pack with a textures/ section and a loose HD pack folder, which wins, and can a MEP textures/ section simply be a hires.txt tree handed to the existing loader? Left undecided, F2 (hires.txt GB/SMS extension) and F3 (MEP textures/) will each grow their own texture-loading path.

## Decision
Decide that MEP's textures/ section is an envelope over the existing hires.txt format and delegates to HdPackLoader rather than parsing textures itself, and state an explicit precedence rule (e.g. loose HD pack folder overrides an installed MEP pack) in MEP-v1.md so EnhancementPackManager's precedence logic and the HD Pack loader agree.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
