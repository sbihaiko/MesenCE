# ADR-0150: The client and CI now share pack_host_allowlist.json as "the single s...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during Execute/T1: The client and CI now share pack_host_allowlist.json as "the single source of truth", but enforce very different trust boundaries around it. fetch_pack.py's module docstring states the gate's whole point: "requests/curl -L would happily follow a redirect from an allowed host to an arbitrary one; here every redirect target is re-validated against the same allow-list before being followed", plus a private/loopback/link-local IP check that it calls "what actually stands in for 'no SSRF', not the hostname string match by itself", plus a size cap and the google-drive two-step. The fetcher applies MatchHost to the first hop only and lets HttpClient auto-follow up to 50 redirects with no re-check, no DNS/IP check and no size cap. Content integrity still holds (sha256 is verified before anything is kept), so the residual exposure is the client being steered into an HTTPS request to an arbitrary host - including a metadata address - chosen by whoever controls an allow-listed URL. Worth an explicit decision recorded against ADR-0138: which of CI's four download-side controls the shipped client is expected to mirror, and which are deliberately CI-only because the catalog is maintainer-curated and the payload is hash-pinned.

## Decision
Decide and record the client-side download trust contract. Minimal option: an HttpClientHandler { AllowAutoRedirect = false } loop that re-runs MatchHost per hop (mirroring open_validated) plus a max-bytes guard derived from the catalog's Size, moved into a small shared helper both the primary and dep download paths use. Alternative: state in the ADR that first-hop gating + sha256 pinning is the intended client bar and that per-hop/SSRF/size controls stay CI-only, so the divergence stops looking like an oversight.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
