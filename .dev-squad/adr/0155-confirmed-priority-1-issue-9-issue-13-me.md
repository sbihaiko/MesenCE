# ADR-0155: CONFIRMED, PRIORITY 1 (issue 9 + issue 13, merge into one decision). ...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during auditor-b: CONFIRMED, PRIORITY 1 (issue 9 + issue 13, merge into one decision). Read the T1 branch source: `DownloadToVerifiedFileAsync` does `using HttpClient client = new(); byte[] data = await client.GetByteArrayAsync(url)` after a single first-hop `MatchHost` check. That means the default handler follows up to 50 redirects with no per-hop re-validation, no private/loopback/link-local IP check, and no size cap — while `scripts/fetch_pack.py`'s own docstring states those controls are the point of the gate. The critic understated it: `GetByteArrayAsync` also buffers the entire body in memory *before* sha256 is computed, so 'content integrity still holds' covers tampering but not availability — a hostile redirect from an allow-listed URL can OOM the emulator with bytes that are then discarded. Separately, `CatalogUrl` is a hard-coded const that is the one HTTP GET in the class NOT passed through `MatchHost`, so the catalog and the artifacts trust different things. Decide both as one contract: which of fetch_pack.py's four download-side controls the client mirrors, and whether the allow-list is the single trust boundary for every GET in the class. The fix is cheapest right now because T1 is not on main.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
