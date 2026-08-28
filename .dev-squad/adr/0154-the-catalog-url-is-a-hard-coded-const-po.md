# ADR-0154: The catalog URL is a hard-coded `const` pointing at `raw.githubuserco...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during Execute/T1: The catalog URL is a hard-coded `const` pointing at `raw.githubusercontent.com/sbihaiko/MesenCE/main/docs/community-packs.json`. That pins the shipped client to one fork's `main` branch with no override (no config key, no environment/CLI escape hatch), and — unlike every download URL in this class — it is not itself gated through `CommunityPackHostAllowlist.MatchHost`, so the catalog fetch and the artifact fetches trust different things. ADR-0138 §37 and the new player-shell ADRs (0139-0141, "one-slot catalog") both speak to catalog identity/origin binding, so where the catalog origin lives is a decision worth recording rather than a constant.

## Decision
Record the catalog origin as an explicit decision: either move it into `EnhancementPackConfig` (user/CI-overridable, then validated through MatchHost like any other URL) or state in an ADR amendment that it is deliberately a compile-time constant bound to the upstream fork, and route it through MatchHost anyway so the allow-list is the single trust boundary for every HTTP GET in the class.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
