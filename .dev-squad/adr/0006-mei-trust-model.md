# ADR-0006: MEI trust model — mandatory checksum verification, HTTPS-only, zip-traversal rejection, confirmation for non-default indexes

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose (consolidates former ADR-0010): F4's Pack Browser is the first outbound-network plus untrusted-archive-extraction path in the UI — it fetches federated manifests from user-configurable third-party URLs, downloads the .zip artifacts they point to, and installs them locally. The spec lists an artifact checksum in the MEI manifest but does not make verification a contract, and no trust model is specified: whether install MUST refuse a checksum mismatch, whether URLs are HTTPS-only, how zip path traversal is prevented on extraction, and what happens when a non-default manifest URL is added.

## Decision
State the trust model in MEI-v1.md as RFC 2119 MUSTs and enforce it in MeiManifestClient: (1) the client MUST verify the declared artifact checksum before an artifact is extracted, activated, or written to disk, and MUST reject on mismatch; (2) manifest and artifact URLs MUST be HTTPS; (3) extraction MUST reject, after path normalisation, any zip entry escaping the pack directory; (4) installing from a manifest URL that is not the default official index requires explicit user confirmation.

## Consequences
The trust decisions are contract, not client implementation detail — third-party MEI clients inherit the same rules. Slightly more friction when adding custom indexes, by design.

## Alternatives
Checksum as advisory metadata (spec-compliant clients could install tampered artifacts). HTTP allowed with a warning (downgrade/MITM surface on an auto-install path).
