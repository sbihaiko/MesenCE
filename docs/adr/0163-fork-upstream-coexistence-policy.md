# ADR-0163: Fork–upstream coexistence — mechanical ownership tiers, merge-over-rebase, and a PR-based sync flow

- Status: accepted (2026-09-06, by the user; implementation = the sync infra in this ADR's Decision items 1–6)
- Date: 2026-09-06
- Related: `docs/roadmap/AGENTS.md` (product consoles), ADR-0158 (deleted nothing — recorded so this ADR does not misattribute the fork's deletions)
- Supersedes / amends: CONTRIBUTING.md "Product branch is `main`" — its blanket "do not `git merge upstream/master` into `main`" rule, replaced by the merge-based flow below

## Context

The fork (`sbihaiko/MesenCE`) exists to build an enhancement ecosystem on top
of upstream `nesdev-org/MesenCE`, so it must keep being able to merge
upstream from time to time without turning into a conflict hell. Upstream is
slow-moving but is not dead: in the last year it touched 1,441 files, led by
`UI/Localization/resources.en.xml`, `Core/NES/NesPpu.cpp`, the Mappers tree,
`Core/Shared/SettingTypes.h` and the Debugger views.

Measured on 2026-09-06, the fork's divergence from the live merge-base is a
clean three-way picture:

- `upstream/master` (`73be5b58`, 2026-09-05) **is an ancestor of `main`**;
  the fork is ahead by 677 commits and upstream has nothing the fork lacks.
  There are therefore **zero pending conflicts**; every conflict risk is on
  the next upstream commit, not on the fork's history.
- Relative to that merge-base the fork has **added 448 files** (tier A),
  **modified 198** (tier B), **deleted 390** (tier D) and **inherited 1,774
  untouched** (tier C). Total tracked: 2,420. (Tiers are a moving function of
  the merge-base; `scripts/upstream_tiers.py` recomputes them — the counts
  here are the 2026-09-06 measurement only.)

**Correction of a misattributed premise.** This review effort was framed as
"the 393 files deleted by ADR-0158". That framing is wrong and is corrected
here so the policy is not built on it: ADR-0158 ships **no code and no
deletions** (it declined `NES_ONLY`/`LessUI` build modes and its only
deliverable was a measurement). The 390 deleted files are the cumulative
result of the console reduction and the later consolidation slices. The
delete/modify policy below governs that deleted set regardless of which
slice produced each deletion.

**Upstream heat is the second axis, and it splits cleanly.** Overlap of each
tier with the 1,441 files upstream touched in the last year:

| Tier | Size | Touched by upstream / yr | Meaning |
|---|---|---|---|
| A (added by us) | 448 | **0** | pure fork surface; upstream has no path to conflict |
| B (modified by us) | 198 | 175 | modify/modify risk only if upstream edits again |
| C (inherited untouched) | 1,774 | 974 | upstream edits land **clean** — we never touch these |
| D (deleted by us) | 390 | 277 | delete/modify risk if upstream edits again |

The D∩heat surface is 100% the removed-console footprint: 229 files in the
removed cores (`Core/SNES/`, `Core/PCE/`, `Core/WS/`) and 48 files of their
removed UI chrome (SNES/PCE/WS config views, status view-models, controller
views, SPC/WS save windows, per-console `Interop/ConsoleState`). None of it
is product code — the product consoles are NES, GB/GBC, SMS and GBA
(`docs/roadmap/AGENTS.md`), none of which appear in D. The 113 remaining D
files upstream has not touched in a year are dormant and will conflict only
if upstream revives them.

This gives a workable physics: keep upstream's future edits landing in C
(clean by construction), make B and D conflicts mechanical and
pre-enumerable, and never let a merge resurrect a deleted console.

**Superseded guidance.** CONTRIBUTING.md has long said "do not
`git merge upstream/master` into `main`" on the belief that a merge
reintroduces the dropped consoles (SNES incl. SGB, PC Engine, WonderSwan,
ColecoVision). That belief is exactly the delete/modify problem this ADR
solves: a merge does not reintroduce a deleted console unless someone
resolves the conflict by restoring the file, and tier D's uniform "keep the
deletion" rule forbids that. Under this ADR a merge brings upstream's
*changes* and never upstream's removed-console *files*; CONTRIBUTING.md is
updated accordingly, and GitHub's "Sync fork" button stays discouraged only
because it offers no rerere/auto-resolution and no PR gate.

## Decision

**A "tiers + heat + merge-not-rebase + PR sync" policy, computed
mechanically and never hand-maintained.**

1. **Ownership tiers, recomputed, never stored.** A single script
   (`scripts/upstream_tiers.py`) derives the sets from the live merge-base,
   exactly as specified:
   - **A** = `git diff --diff-filter=A --name-only <merge-base> HEAD`
     (added by us);
   - **B** = `--diff-filter=M` (modified by us);
   - **C** = the rest of `git ls-files` — inherited files we have never
     touched;
   - **D** = `--diff-filter=D` (deleted by us) is reported alongside as the
     delete/modify watchlist, even though it is not a tier of tracked files.
   The script annotates every listed file with its upstream heat (commit
   count in `git log <upstream> --since=1.year --name-only`). Nothing is
   committed as a frozen list; the tiers are a function of the current
   merge-base and are recomputed on every use.

2. **Change policy by tier.** Standing rule for the fork's own commits
   (and the inherited-code review that consumes these tiers):
   - **Tier A** — free to edit, refactor, delete.
   - **Tier B** — edits allowed, but where the file is upstream-hot keep the
     hunk as narrow as the change allows and prefer additive hunks that do
     not reflow upstream-shaped regions; every touch re-forkes that file's
     merge.
   - **Tier C** — defect fixes only (memory safety, undefined behavior,
     integer overflow, leak, race, injection). No renaming, reindenting,
     include reordering, function-splitting or readability passes; those
     become report items, not patches. Rationale: C is where upstream's
     edits apply cleanly, so the cheapest future merges are the commits that
     never touch C. Tier C files that are also upstream-hot are
     report-only unless the defect is an exploitable vulnerability, which is
     then extracted into a new Tier A file with a one-line call left in the
     upstream file.
   - **Tier D** — never re-added to satisfy a merge. Every delete/modify
     conflict on a D file resolves the same way: **keep the fork's
     deletion**. Resurrecting a removed-console file "because the merge
     wanted it" is exactly how a fork drifts into conflict hell.

3. **Rerere is policy, not preference.** `rerere.enabled` and
   `rerere.autoUpdate` are both `true` on the working clone and must be `true`
   on any clone or CI runner that merges upstream. The first encounter of
   each delete/modify conflict on a D file is resolved as a deletion and
   recorded by rerere; every later sync replays that resolution silently.
   Over time the 277 live D∩heat conflicts cost one manual resolution each
   and then vanish from the review loop.

4. **`main` merges; it never rebases.** Upstream history is brought in with
   `git merge upstream/master`. A fast-forward is impossible in practice —
   upstream never contains fork commits, so upstream can never be a
   descendant of `main` — and every sync is therefore a true merge commit
   that keeps both parents and advances the merge-base. `pull.rebase` stays
   off. Rebasing `main` is forbidden because it rewrites the fork's commits
   and makes every future three-way merge re-examine the entire divergence.

5. **`Upstream-Delta:` trailer.** Any commit that touches a Tier C file (or
   a Tier B file that is upstream-hot) must carry, in the body, a
   `Upstream-Delta:` line stating why the fork diverges and the
   smaller-upstream-surface alternative that was considered. The check
   `scripts/checks/verify_upstream_delta.py` scans a revision range and
   fails on any commit that touches C without the trailer. It runs as part
   of the sync flow and of the inherited-code review; it is not a commit-msg
   hook, because the trailer is only meaningful against the tier sets that
   exist at review time.

6. **Sync flow.** `scripts/sync-upstream.sh` fetches `upstream`, recomputes
   tiers, prints the *predicted* conflict set for the commits upstream is
   about to bring (D∩new, B∩new), then merges `upstream/master` into `main`.
   The scheduled `.github/workflows/sync-upstream.yml` runs it
   non-interactively on a cadence: when upstream has advanced past the
   merge-base it creates a `sync/upstream/<date>` branch, applies the merge
   there, and opens a **PR to `main`** whose body lists the predicted
   delete/modify and modify/modify conflicts and their standing resolutions.
   The workflow never merges to `main` itself — the PR is the human gate and
   lets the normal CI run against the merged tree. When upstream has not
   advanced, the run is a no-op.

## Consequences

- **Merge cost stays bounded.** Upstream edits land in C (clean by
  construction, 1,016/yr) or produce a mechanical, pre-listed, rerere-replayed
  conflict in B or D. Each sync is a small, reviewable diff instead of a
  full-divergence reconciliation.
- **The delete/modify debt is finite and one-shot.** 277 live D∩heat files
  cost one recorded resolution each, then rerere carries them forever. The
  "393 deleted files" premise, corrected to 390, is not a number to fear: it
  is a fixed list of removed-console files whose resolution is always the
  same verb.
- **Costs.** A standing daily workflow and PR to triage; the review effort
  must actually honor the Tier C rule (every "helpful" C refactor is a
  future conflict it pays for); B and D files the fork keeps editing accrue
  narrow merge surface each time.
- **Traps.** Never un-delete to resolve a conflict; never rebase `main` to
  "clean up"; never hardcode the tier lists or the heat snapshot — both are
  functions of a moving merge-base and must be recomputed, which is why the
  tiers live in a script and not in this ADR's table.

## Alternatives

**Rebase the fork's work onto upstream on every sync.** Rejected: rewrites
678 commits, makes the divergence re-examine itself on every sync, and
requires force-push coordination across the fork's clones. Merge preserves
the fork's history and confines reconciliation to the actual delta.

**Store the ownership tiers as a versioned allow-list.** Rejected: a checked
list rots the moment the merge-base moves and invites edits to the list
instead of to the code. The tiers must be derivable, so they are derived.

**Let the sync workflow merge straight to `main`.** Rejected: no human gate,
no CI on the merged tree before `main` moves, and the workflow would need
the delete/modify resolutions encoded headlessly. The PR indirection is the
gate and the audit trail.

**Leave the D files to ad-hoc resolution.** Rejected: without a uniform
"keep the deletion" rule, each upstream edit to a removed console invites a
re-litigation of whether SNES/PCE/WS should come back, which is exactly the
conflict hell this ADR exists to prevent.
