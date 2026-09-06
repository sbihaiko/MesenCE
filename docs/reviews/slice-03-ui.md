# Slice 3 — UI/ (Avalonia C#, incl. UI/Debugger) — inherited-code review

- Repo `HEAD` reviewed: `2c58e139`; merge-base `73be5b58`.
- Scope: `UI/**` — view models, windows, services, controls, debugger integration/importers, config, utilities. Cross-cuts the C# side of the fork surface (A 5 / B 9 / C 16 findings).
- Method: tier/heat snapshot + nullable-warnings-as-errors Debug headless build as the strict compiler gate (CS8600-style Werrors caught mid-slice); grep over path-building, `async void`, `int.Parse`/`Substring`, event-subscription and image-lifecycle sites.

## Findings

30 total — P0 0, P1 2, P2 22, P3 6. Tiers: A 5, B 9, C 16. Patchable by rule: 16.

## Patched (9 findings, 9 files, +65/−22, 3 commits)

| file | tier/heat | finding(s) resolved | hunk gist | ± |
|---|---|---|---|---|
| `UI/ViewModels/MainMenuViewModel.cs` | B(hot) | [P1] HD-pack install **zip-slip** — rooted/`../` entries escape `HdPacks/<rom>/` (arbitrary write) | every entry path through `LegacyHdPackInstall.NormalizeZipPath`, re-check prefix, refuse null | +21/−8 |
| `UI/Services/CommunityPackInstallService.cs` | A | [P2] 300 MB SHA-256 fetch blocks the dispatcher | `Task.Run` around the fetch | +5/−1 |
| `UI/ViewModels/GamepadTesterViewModel.cs` | A | [P2] circularity keys looked up as Messages → literal `[[lbl…]]` | `GetViewLabel(nameof(InputConfigView), …)` | +4/−4 |
| `UI/ViewModels/HdPackPreviewViewModel.cs` | A | [P2] preview Bitmaps never disposed (leak per selection) | dispose outgoing + `DisposeView()` | +14/−0 |
| `UI/ViewModels/MainWindowViewModel.cs` | B | [P2] `AudioPlayer?.Dispose()` before recreate → dead player bound after NSF→NSF | dispose only on the replace path | +10/−4 |
| `UI/Debugger/Integration/ElfImporter.cs` | B | [P2] unbounded `int.Parse` digit run → OverflowException aborts import | `int.TryParse` | +5/−1 |
| `UI/Debugger/Integration/WlaDxImporter.cs` | B | [P2] unguarded `_sourceFiles[fileId]` → KeyNotFoundException aborts import | `TryGetValue` + null guard | +9/−2 |
| `UI/Debugger/Utilities/DebugWorkspaceManager.cs` | B | [P2] extension-less drop → `Substring(1)` throws | length check first | +3/−1 |
| `UI/Debugger/ViewModels/RegisterViewerWindowViewModel.cs` | B(hot) | [P3] X24 truncation uses `> 7` threshold → 7-hex values untruncated | `> 6` | +2/−1 |

Commits: `f8af364c` (zip-slip), `8be76760` (disposal/localization/off-UI-thread), `9d3c1414` (debugger importers/register view).

## Reported, not patched (21)

Reachable crash/robustness (C+hot, report-only):
- `UI/Windows/SelectStorageFolderWindow.axaml.cs:39` [P1] first-run migration `async void` with no try/catch — read-only/TCC target crashes setup.
- `UI/Debugger/WatchManager.cs:197` [P2] unbounded array-watch count → OverflowException crash, persisted.
- `UI/Debugger/Integration/NesasmFnsImporter.cs:46` [P2] uint `address-0x8000` underflow → bogus PRG label; `:35` [P2] empty value column → crash.
- `UI/Debugger/Utilities/TblLoader.cs:28` [P2] shift ≥ 64 masked → long TBL keys corrupt the table; `:23` [P3] malformed line silently discards the file.
- `UI/Debugger/Controls/PictureViewer.cs:283` [P2] `ExportToPng` async void, unwritable destination crashes.
- `UI/Utilities/LoadRomHelper.cs:96` [P2] async void patch-dir enumeration crash.
- `UI/Utilities/RomTestHelper.cs:177` [P3] shift ≥ 64 → 9+ hex-digit names decode wrongly (false FAIL).
- `UI/ViewModels/SetupWizardViewModel.cs:113` [P2] single-string `Arguments` chmod re-split on space.
- `UI/Debugger/Controls/PaletteSelector.cs:272` [P3] highlight 1/16 too far left.
- `UI/Controls/StateGridEntry.axaml.cs:165` [P3] preview bitmap leak per refresh.
- `UI/Controls/SoftwareRendererView.axaml.cs:56` [P3] surface leak on every resolution/console change.

Races / lifecycle:
- `UI/ViewModels/SelectStorageFolderViewModel.cs:58` [P2] `IsCopying` set inside Task.Run → cancel-guard window + off-thread PropertyChanged.
- `UI/Windows/MainWindow.axaml.cs:569` [P2 B race] `tcs.Task.Wait()` on emu thread with UI-thread completion → deadlock.
- `UI/Debugger/Utilities/DebugWindowManager.cs:137` [P2 B race] `InvokeAsync(...).Wait()` both-threads stall.

Eligible-but-not-selected this pass (patchable by rule; kept to keep the diff reviewable — good next candidates):
- `UI/Utilities/ApplicationHelper.cs:88` [P2 C cold injection] Linux `OpenBrowser` splices URL into `sh -c` with incomplete escaping — shell expansion/wrong target.
- `UI/Debugger/Utilities/DynamicTooltip.axaml.cs:256` [P2 C cold leak] per-hover `Invalidated` subscription never removed.
- `UI/Logic/LegacyHdPackInstall.cs:186` [P2 A] nested-zip unwrap buffers whole inner zip before the 2 GiB gate.
- `UI/Windows/EnhancementPacksWindow.axaml.cs:91` [P2 A] Restore continuation touches a disposed VM after close.
- `UI/Config/FileAssociationHelper.cs:98` [P2 B] Linux mime/desktop registration breaks on a path with a space.
- `UI/Debugger/WatchManager.cs` listed above (C+hot). 

## Verification

`make ui` + headless-ui-tests (nullable Werror Debug) + unit-tests all green. Mid-slice the Werror Debug build caught a CS8600 introduced by the WlaDxImporter `TryGetValue` patch (unit-tests don't dual-compile that file); fixed with `out SourceFileInfo? && src != null` before the slice closed — the gate earned its keep.

## Before / after (0–10)

| axis | before | after | supporting numbers |
|---|---|---|---|
| quality | 6 | 8 | 9/30 patched incl. the single P1 injection; races/leaks in A-tier VMs closed; C+hot items (16) stay reported per ADR-0163 |
| performance | 7.5 | 8 | 300 MB SHA-256 fetch moved off the dispatcher; image-dispose fixes remove unbounded per-selection leak; no hot-path cost added |
| readability | 7.5 | 7.5 | +65/−22 across 9 files; each fix is a small guard/refactor in place, matching local idiom (comments where a trap is subtle) |
| security | 5.5 | 7.5 | before: P1 zip-slip arbitrary file write on a malicious HD pack; after: all zip-extraction entry paths normalized through the shared sanitizer; Linux shell-injection (`OpenBrowser`) still reported as an eligible candidate |
