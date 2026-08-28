# ADR-0159: CONFIRMED but LOW severity, and raised three times (issues 1, 2, 10) ...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during auditor-b: CONFIRMED but LOW severity, and raised three times (issues 1, 2, 10) with three mutually incompatible fixes — this is the run's clearest noise pattern, not three findings. Code confirms it: `EnhancementPacksWindow.EnsureCommunityPackAutoInstallConsent()` is a public static on a Window that mutates config and Saves, and it currently has NO caller on HEAD (T3 never landed), so it is dead code. The spec explicitly sanctioned the placement, so critics keep re-litigating a decision that was already made — the cure is to record it, not to re-raise it. Note the conflict: issue 1 wants CommunityPackInstallService to show the dialog itself, which would directly violate the Services boundary if that boundary is written as 'Services must not touch Avalonia'. Decide dialog placement and the Services boundary in the same sitting or the fix for one breaks the other. Since there is no caller yet, moving the helper to a small UI/Services presenter (issue 2's option) costs nearly nothing today and rises in cost the moment T3 lands.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
