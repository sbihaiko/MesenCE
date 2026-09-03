# ADR-0004: hires.txt extension spec is published as v1-draft pending community review, not final v1

- Status: accepted
- Date: 2026-08-24

## Context
Raised during spec: The PRD explicitly states this extension 'deve ser discutida com a comunidade HDNes/Mesen antes de congelar a v1' (must be discussed with the community before freezing v1), unlike the other three specs (ESP/MEP/MEI) which it treats as ready to formalize outright. The spec's deliverable nonetheless produces this as a golden-example-backed, script-validated 'v1' file on the same footing as the other three.

## Decision
Mark this document's status distinctly (e.g. 'v1-draft / proposal, pending community review') rather than presenting it with the same finality as the other three specs, so the artifact itself does not overstate consensus the PRD says does not exist yet.

## Consequences
Downstream work (F2 tile capture, ADR-0002) builds against a document that is honest about its stability; a community-driven change to the format is a draft revision, not a breaking change to a frozen v1.

## Alternatives
Ship as final v1 and version-bump on community feedback: cheaper now, but externally reads as the project freezing a format the PRD promised to discuss first.
