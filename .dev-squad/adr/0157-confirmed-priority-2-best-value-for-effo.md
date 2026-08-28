# ADR-0157: CONFIRMED, PRIORITY 2, best value-for-effort (issue 12). `GetContaine...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during auditor-b: CONFIRMED, PRIORITY 2, best value-for-effort (issue 12). `GetContainerName` at CommunityPackInstallCoordinator.cs:160-169 is the security-critical guard in this whole flow — submitter-influenced `entry.Name` reaching both `Directory.Delete(outFolder, true)` and the native extraction target — and it is the single piece of the flow with zero test reachability, purely because it landed in Services instead of UI/Logic. The sanitization is actually well done (invalid-char swap, dot-only rejection, trailing dot/space strip, 96-char cap with post-truncation re-trim, plus the rooted-path assertion in `ResolveOutFolder`), which is exactly why it deserves to be pinned by tests before someone 'simplifies' it. Extract the pure part to a host-free UI/Logic/CommunityPackContainerName.cs so it dual-compiles into UI.Tests and becomes the single source of truth for the DisabledPacks key; leave `ResolveOutFolder` in Services as the ConfigManager-aware wrapper. ~10 lines of movement.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
