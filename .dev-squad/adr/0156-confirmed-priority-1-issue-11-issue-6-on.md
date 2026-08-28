# ADR-0156: CONFIRMED, PRIORITY 1 (issue 11 + issue 6, one decision). `CommunityP...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during auditor-b: CONFIRMED, PRIORITY 1 (issue 11 + issue 6, one decision). `CommunityPackInstallCoordinator.Install(entry, primaryPackPath, resolvedDepPaths)` takes an already-downloaded, already-verified path, and `EvaluateGates` runs `CommunityPackConsentState.Evaluate` only after that — so in the assembled flow an unconsented machine performs the catalog fetch AND the artifact download, and only the install is blocked. That inverts ADR-0138 §38, whose whole point is that consent gates the first automatic download. Issue 6 is the same gap seen from the other side: nothing short-circuits a re-fired ROM-load hook before the network, and the `.mep-install.json`/§43 gate is only reached post-download. Fix them together in T3, which has not landed: `CommunityPackInstallService` evaluates consent and an in-memory per-session (rom sha1, entry sha256) attempt set BEFORE calling the fetcher; the coordinator's existing `NeedsConsent` outcome then becomes documented defense-in-depth rather than the primary gate. Record which layer owns the §38 gate so the two checks cannot drift.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
