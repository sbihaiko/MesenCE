# ADR-0146: Auto-load every accepted community pack registered in a GitHub issue, whenever possible

- Status: accepted
- Date: 2026-09-01

## Context
Community HD/MEP packs are submitted via the
`.github/ISSUE_TEMPLATE/community-pack.yml` form and tracked on the
"MesenCE Community Packs" project board. The validate workflow
(`community-pack-validate.yml`) lints and classifies each submission, and an
`accepted` verdict (label `pack:valid`) lands a row in
`docs/community-packs.md` / `docs/community-packs.json` for the client's
auto-install hook (ADR-0138). Today the client's FIRST automatic download is
gated behind an explicit user consent:
`EnhancementPackConfig.CommunityPackAutoInstallConsentGiven` (default `false`)
consumed by `UI/Logic/CommunityPackConsentState.cs`, per ADR-0138 §38, §51 and
§54. That gate means a registered, accepted pack for a loaded ROM is NOT
installed or loaded unless the user has individually opted into auto-install —
the pack silently does not appear even though it is in the catalog and matches
the ROM by SHA1 (ADR-0003 / ADR-0039). This is exactly what happened for
Donkey Kong (issue #144): the catalog entry carries the matching SHA1
`D222DBBA5BD3716BBF62CA91167C6A9D15C60065`, but `CommunityPackAutoInstallConsentGiven`
was still `false`, so the download never ran and the emulator fell back to a
local bootstrap auto-only pack.

## Decision
Every community pack registered in a GitHub issue and accepted onto the
"MesenCE Community Packs" board (verdict `accepted`, label `pack:valid`, i.e.
present as a row in `docs/community-packs.json`) MUST be automatically
downloaded, installed and loaded by the client whenever possible. "Whenever
possible" means: the pack is reachable from an allow-listed host (ADR-0138
§41), matches the loaded ROM (No-Intro SHA1 per ADR-0003 / ADR-0039, or an
optimistic texture/BPS match per ADR-0145), and is not disabled by the user.
No first-run or per-pack consent dialog may block this; the
`CommunityPackAutoInstallConsentGiven` gate (and the consent prompt in
`EnhancementPacksWindow.EnsureCommunityPackAutoInstallConsent`) is removed for
the auto-install path. This supersedes the consent-gate clauses of ADR-0138
(§38 "first-run consent", §51 "consent gate ownership", §54 "consent dialog
placement"). The single master switch remains
`AutoInstallCommunityPacks` (default `true`); turning it off disables every
auto-load, and a per-pack manual disable (by pack_id / container) still
overrides the blanket rule.

## Consequences
- A registered accepted pack for the loaded game is fetched, installed and
  applied automatically on ROM load — no consent dialog, no per-pack opt-in.
- `CommunityPackConsentState` and `CommunityPackAutoInstallConsentGiven`
  become dead for the auto-install path and should be removed so the
  `Evaluate` path always yields `CanDownloadNow=true` while
  `AutoInstallCommunityPacks` is on.
- The auto-installed accepted pack wins over any local bootstrap auto-only
  pack (human/accepted art > auto upscale; ADR-0049 sibling-folder precedence
  and ADR-0050 auto backgrounds), so a vanilla auto pack no longer masks
  accepted community art.
- Trust framing: downloading a pack from an allow-listed host is already the
  accepted model (ADR-0138 §4, §41); dropping consent restores the behavior
  implied by the `AutoInstallCommunityPacks` default of `true`. The catalog
  (and the `pack:invalid` path / `pack:needs-review` label) becomes the
  trust-boundary: a bad pack is removed from the catalog, not gated behind a
  per-user prompt.
- Risk: accepted packs are treated as trusted without a per-install prompt; a
  malicious/broken pack would be cleaned up through the catalog verdict flow,
  not by consent, so the allow-list + SHA1/NI matching are the safety net.

## Alternatives
- Keep the first-run consent gate (status quo) — rejected: it silently blocks
  the product promise that registered packs auto-load, requires per-user
  opt-in, and caused the Donkey Kong (#144) stall.
- Auto-load only packs the user downloaded manually — rejected: defeats the
  "registered pack auto-loads" directive and fragments behavior between
  catalog and manual installs.
- Auto-load with no catalog or host restriction — rejected: the allow-list
  host restriction (ADR-0138 §41) and SHA1/NI matching (ADR-0003 / ADR-0039)
  already bound what may be fetched and installed, so removing consent does
  not require loosening trust.
