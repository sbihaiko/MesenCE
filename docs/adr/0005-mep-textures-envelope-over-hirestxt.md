# ADR-0005: MEP textures/ is an envelope over hires.txt delegating to HdPackLoader, with explicit precedence

- Status: accepted
- Date: 2026-08-24

## Context
Raised during decompose: MEP introduces a second, parallel enhancement-content system alongside the existing hires.txt HD Pack stack (HdPackLoader/HdNesPack/HdPackBuilder), and the spec defines no relationship between them: if a game has both an installed MEP pack with a textures/ section and a loose HD pack folder, which wins? Left undecided, F2 (hires.txt GB/SMS extension) and F3 (MEP textures/) will each grow their own texture-loading path.

## Decision
MEP's textures/ section is an envelope over the existing hires.txt format and delegates to HdPackLoader rather than parsing textures itself. State an explicit precedence rule in MEP-v1.md so EnhancementPackManager's precedence logic and the HD Pack loader agree; the normative text is MEP-v1 §2.1 rule 7 and §5.1 (sibling folder → loose HD Pack → central storage), not this ADR.

**Extended by ADR-0040 and ADR-0049.** This ADR only records the envelope decision; the precedence chain grew from the original two-tier example (loose HD pack over installed MEP pack) to the three-tier rule above when the sibling-folder origin was added.

## Consequences
One texture-loading path instead of two; the F2 format extension automatically benefits MEP packs. The precedence rule becomes user-visible behaviour and must be documented in MEP-v1.md, not just implemented.

## Alternatives
Independent MEP texture parser: duplicates HdPackLoader and forks the format. No precedence rule: whichever loader runs last wins, nondeterministically.
