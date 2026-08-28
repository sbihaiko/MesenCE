# ADR-0162: DOWNGRADE — closest thing to noise in this batch (issue 7). I read `s...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during auditor-b: DOWNGRADE — closest thing to noise in this batch (issue 7). I read `scripts/checks/verify_core_no_http_client.sh`: it strips // and /* */ comments line-for-line to preserve line numbers, fails non-vacuously if Core/ is missing, matches curl includes / curl_easy_* / CURLOPT_* / CURL* handles / a class named HttpClient, and reads the real tree. The invariant is 'do not ADD HTTP to a tree that has today none', and the grep catches every realistic way that would appear in a hand-written commit. The proposed link-symbol assertion is disproportionate to that risk, and the critic's own text concedes it is 'worth an ADR only if the boundary is expected to come under real pressure' — it is not. Recommend explicitly closing this rather than leaving it open to be actioned by a later run.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
