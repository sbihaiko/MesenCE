# ADR-0010: F4 introduces the first outbound-network plus untrusted-archive-extra...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: F4 introduces the first outbound-network plus untrusted-archive-extraction path in the UI (fetch federated manifests from user-editable URLs, download a .zip, install it locally). No trust model is specified: whether the MEI artifact checksum is verified before install, how zip path traversal is prevented on extraction, and what happens when a non-default manifest URL is added.

## Decision
State the trust model in MEI-v1.md and enforce it in the client: mandatory checksum verification against the manifest entry before an artifact is written to disk, path-normalisation rejection of any zip entry escaping the pack directory, and an explicit user confirmation when installing from a manifest URL that is not the default official index.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
