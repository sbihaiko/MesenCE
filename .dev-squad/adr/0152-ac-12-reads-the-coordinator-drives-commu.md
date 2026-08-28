# ADR-0152: AC-12 reads "the coordinator drives CommunityPackConsentState before ...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during Execute/T2: AC-12 reads "the coordinator drives CommunityPackConsentState before any download proceeds", but the coordinator's entry point accepts an *already downloaded and sha256-verified* primaryPackPath plus an already-verified dep-path map (T1's output shape). The consent gate therefore runs strictly after the network fetch in the assembled flow, which inverts ADR-0138 §38's intent: the first automatic download is supposed to be what consent gates. As written, an unconsented user's machine still performs the catalog fetch and the artifact download; only the install is blocked.

## Decision
Make CommunityPackConsentState.Evaluate the first thing CommunityPackInstallService (T3) does, before invoking CommunityPackCatalogFetcher at all, and keep the coordinator's own consent check as the defense-in-depth second gate it now is. Worth recording which layer owns the §38 gate so the two checks do not drift.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
