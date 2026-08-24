# ADR-0006: The Pack Browser fetches manifests from user-configurable third-party...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: The Pack Browser fetches manifests from user-configurable third-party URLs and installs the .zip artifacts they point to. The spec lists an artifact checksum in the MEI manifest but does not make verification a contract: whether install MUST refuse an artifact whose checksum mismatches, and whether the manifest URL list is HTTPS-only, is an unstated trust decision baked into the client's design.

## Decision
State in MEI-v1.md as a RFC 2119 MUST that a client verifies the declared artifact checksum before extracting or activating a pack and rejects on mismatch, and that manifest and artifact URLs MUST be HTTPS; have MeiManifestClient enforce both.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
