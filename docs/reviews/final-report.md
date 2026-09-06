# Fork/upstream inherited-code review — final report

Review of the code `sbihaiko/MesenCE` inherited from `nesdev-org/MesenCE`, under the hard constraint that the fork stays mergeable with upstream. Baseline `HEAD` `2c58e139`; fork/upstream merge-base `73be5b58` (upstream/master is an ancestor of HEAD).

## 1. Method & policy (ADR-0163)

Ownership tiers are computed mechanically from the merge-base (`scripts/upstream_tiers.py`): A = fork-added, B = fork-modified, C = inherited pristine, D = fork-deleted. Upstream heat (`git log upstream/master --since=1.year`) is the second axis. Working rule for "hot": file under `Core/Debugger/`, `Core/NES/Mappers/`, `Utilities/Audio/`, **or** per-file heat ≥ 5/yr.

Patch policy per tier (binding):
- Tier A/B — fix normally (minimal hunks, merge surface minimized).
- Tier C — only real defects (memory safety, UB, integer overflow, leak, race, injection); cosmetic changes never.
- Tier C + hot — report-only unless the defect is an *exploitable* vulnerability.
- Tier C commits touching guarded files carry an `Upstream-Delta:` trailer (enforced by `scripts/checks/verify_upstream_delta.py`); merges (never rebase) on main with rerere on (`scripts/sync-upstream.sh` + scheduled `sync-upstream.yml`).

## 2. Findings — aggregate

| | findings | P0 | P1 | P2 | P3 |
|---|---|---|---|---|---|
| Utilities/SevenZip/Lua | 11 | 0 | 3 | 8 | 0 |
| Core non-Debugger | 21 | 0 | 3 | 17 | 1 |
| UI (incl. UI/Debugger) | 30 | 0 | 2 | 22 | 6 |
| Core/Debugger | 9 | 0 | 1 | 7 | 1 |
| **Total** | **71** | **0** | **9** | **54** | **8** |

**Disposition: 27 finding-instances fixed across 23 files (+201/−53 in 12 commits); 44 reported, not patched** (tier-C-hot, latent/needs-runtime-validation, or eligible-but-deferred — see per-slice reports for each with file:line and rationale).

By tier of what was fixed: 12 tier-C-cold files, 8 tier-B, 3 tier-A. All C fixes were real defects on cold files; every patch is a minimal, single-purpose hunk with an explanatory comment where the trap is subtle. No tier-C-hot file was modified.

## 3. Verification gates — before / after

| gate | before (baseline `2c58e139`) | after (HEAD) | Δ |
|---|---|---|---|
| `make core` | clean (clang `-Wall` C++17) | clean, no new warnings | 0 |
| `make ui` | clean | clean | 0 |
| `make core-unit-tests` | 523 PASS | 523 PASS | 0 |
| `make unit-tests` | 427 PASS | 427 PASS | 0 |
| `make headless-ui-tests` | 15 PASS | 15 PASS | 0 |
| `make doc-checks` | PASS | PASS | 0 |
| `ruff check .` | 0 issues | 0 issues | 0 |
| `verify_upstream_delta HEAD~13..HEAD` | n/a (new gate) | **PASS — 11 guarded commits all carry `Upstream-Delta:`** | new |

The null deltas are the point: fixes are guards that change no observable behavior, and the headless/build gates confirm no regression. One mid-slice CS8600 (nullable Werror Debug build) introduced by the `WlaDxImporter` patch was caught by `make headless-ui-tests` where `make unit-tests` did not compile the file — fixed before the slice closed.

**Merge-cheapness (ADR-0163):** upstream/master is still an ancestor of HEAD (`git merge-base --is-ancestor upstream/master HEAD` → true; behind 0). A `git merge --no-commit --no-ff upstream/master` therefore resolves trivially on a throwaway branch.

## 4. Commit inventory (13, all local — push not authorized)

`b09b91a4` chore(upstream): ADR-0163 coexistence policy, tiers tooling, PR-based sync — then, oldest→newest by slice:

1. `0a3eed0c` fix(7z): clamp MemBuffer read/seek … (+19/−4)
2. `5229d5c5` fix(patchers): bound UPS/BPS writes and cap base128 varints (+19/−1)
3. `820f5494` fix(utilities): 64-bit buffer sizes and short-read guards in CRC32/ArchiveReader (+18/−8)
4. `d2db65b7` fix(utilities): guard decompress header read and clamp FastString writes (+34/−9)
5. `e30dd9c0` fix(netplay): reject zero-length messages, out-of-range ports and huge player lists (+16/−2)
6. `a766d434` fix(shared): cap save-state allocations derived from file-supplied sizes (+9)
7. `50f339e0` fix(nes): bound StudyBox tape chunk-header reads (+12)
8. `e58aec16` fix(sms): avoid signed left-shift overflow when sizing the pad (+1/−1)
9. `f8af364c` fix(ui): sanitize HD-pack install paths against zip-slip (+21/−8)
10. `8be76760` fix(ui): view-model disposal, localization lookup and off-UI-thread restore (+30/−9)
11. `9d3c1414` fix(ui-debugger): guard symbol/workspace/ELF importers and 24-bit register view (+14/−5)
12. `9fcc5b48` fix(debugger): defined arithmetic and shift masking in the expression evaluator (+8/−6)

Guard audit: 1 commit (infra) was amended with an `Upstream-Delta:` trailer after the gate correctly flagged `CONTRIBUTING.md` (tier-B hot) without one; the 12 fix commits were replayed over it. Only this session's files are committed; the parallel session's `README.md` / `community-pack-catalog.yml` changes were untouched and remain uncommitted.

## 5. Notes before → after (0–10)

Overall code (the inherited surface): quality 6 → **8**, performance 7.5 → **8**, readability 7 → **7.5**, security 5 → **7.5**. The before/after deltas per slice, with the numbers behind them, are in each per-slice report; the aggregate driver is 27 defect-class fixes (incl. all four reachable P1s: 7z EOF overflow, UPS OOB heap write, netplay length-0 ~4 GB OOB, netplay port OOB — plus the UI P1 zip-slip) against zero behavioral or performance regression, and 44 items honestly left reported because tier-C-hot or latent rather than patched into a wider merge surface.

## 6. Highest-value next steps (each an upstream report or a tier-B/owning fix)

1. Upstream report candidates (tier-C hot, real defects): `NsfeLoader.h` P1, `iNesLoader.cpp` wrap, `NsfLoader.cpp`, `UnifLoader.cpp`, `FdsLoader.cpp`; `GameServer.cpp` race; `LuaApi.cpp` `emu.drawPixels` P1.
2. Eligible-but-deferred (fork side, clean to pick up): `ApplicationHelper.cs` Linux shell-injection, `DynamicTooltip.axaml.cs` leak, `LegacyHdPackInstall.cs` nested-zip OOM, `EnhancementPacksWindow` disposed-VM continuation, `FileAssociationHelper.cs` space-in-path.
3. Need runtime/recorded-footage validation before touching (B-tier HD provenance): the five `SmsVdp`/`GbPpu`/`GbxFooter` items.
