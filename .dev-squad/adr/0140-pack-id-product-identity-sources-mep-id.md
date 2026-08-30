# ADR-0140: pack_id: product identity sources (MEP id field, owner/repo, issue-n, local: fallback) and catalog uniqueness

- Status: accepted
- Date: 2026-08-28

## Context
the consolidated PRD, Part B §3.3 and §3.5 (accepted product text, 2026-08-28). A pack is a product with revisions; content_id (ADR on canonical hash) identifies a revision but makes every version look like a different pack. Competing packs for the same ROM must be distinguishable from revisions of the same pack, in the catalog and in the client's per-ROM preference (P.3). Local drops have no catalog row and today are keyed by container name (ADR-0040/0049). The download allow-list (scripts/pack_host_allowlist.json) includes gists, raw.githubusercontent.com and Google Drive, where no owner/repo exists.

## Decision
pack_id resolution, first match wins: (1) an explicit 'id' field in pack.json — lowercase slug [a-z0-9][a-z0-9-]{2,63}, unique in the official catalog; this is a MEP-v1 minor bump (v1.4) adding 'id' as SHOULD to §3.1 root fields; (2) else, for github.com / codeload.github.com pack URLs, 'owner/repo' lowercased (origin, not tag or release filename); (3) else 'issue-{n}' of the accepted submission — the only option for gist/raw/Drive links without 'id', so product-level deduplication does not exist there (documented non-goal); (4) local containers without 'id': 'local:<container-name>' (the ADR-0040/0049 discovery key). Catalog uniqueness (enforced by community-pack-validate / the catalog generator): one live row per pack_id; same content_id under any pack_id ⇒ byte-duplicate, comment 'duplicate of #N', not listed; same pack_id + new content_id ⇒ candidate for the single slot per the one-slot ADR; different pack_id + different content_id + same ROM sha1 ⇒ both listed (competing). Duplicate submit where pack_id matches another issue: comment pointing at the original and close the newer issue. Client: a local container whose content_id equals a catalog entry adopts that catalog pack_id; a 'local:' preference migrates silently to the catalog pack_id when a matching content_id is later installed. MEI gains additive MAY fields pack_id, content_id (and votes, integer, non-normative like issue) in P.2. Amendment 2026-08-28 (origin binding, PRD Part B §3.3): a pack_id is bound to the origin of its first accepted submission — the owner/repo of the pack URL, or the issue author's GitHub login for hosts without one — stored in mep-meta as pack_origin. A submission claiming an existing pack_id from a different origin is not a revision: it never competes for the slot, is not listed, and receives a comment plus the pack:needs-review label for human triage (a maintainer may re-bind the origin or treat it as a competing pack). Slices: P.2/P.3 of the consolidated PRD, Part B.

## Consequences


## Alternatives

