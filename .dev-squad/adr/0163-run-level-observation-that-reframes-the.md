# ADR-0163: RUN-LEVEL OBSERVATION that reframes the priorities above: T1 and T3 a...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during auditor-b: RUN-LEVEL OBSERVATION that reframes the priorities above: T1 and T3 are not on HEAD. `UI/Services/CommunityPackCatalogFetcher.cs` exists only on branch squad-119e1031a25f-task-T1, `CommunityPackInstallService.cs` was never created, and there is no MainWindow ROM-load hook — grep for `CommunityPackInstall` across UI/Windows and UI/ViewModels hits only a comment. So F6.4b's second half is half-landed: the coordinator (T2) and the consent helper (T4) are on main with no caller. Consequence for triage: the three highest-severity findings (download trust contract, consent-before-download ordering, per-session idempotency key) all live in code that has not shipped yet and cost almost nothing to fix now, versus a rework once the calling layer exists. Before writing more spec, decide whether T1 is cherry-picked and corrected or re-run — the project's own memory notes this exact failure mode (complete work stranded on an orphan branch after a false-negative critic verdict; recover via git fsck rather than re-running).

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
