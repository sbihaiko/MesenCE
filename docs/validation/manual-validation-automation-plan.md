# Automating the remaining manual validations (P.6, P.7, ADR-0142, F6.5)

## Context

`docs/roadmap/PRD-mesence-enhancement-ecosystem.md` lists four
outstanding items whose "Acceptance" column says "manual" or "pending
(manual)":

- **P.7** — Enhancements quick-toggle panel + Welcome/Continue cards:
  "GUI pass on a real display".
- **P.6** — catalog update wired into the overlay: "catalog update
  end-to-end on a real fetch, 'Updated …' toast wording".
- **ADR-0142** — crossfade contract: "click-free listening verification".
- **F6.5** (ADR-0138) — "GUI end-to-end install acceptance (user-supplied
  audio, manual)". (An earlier draft also cited "F6.8"; no such slice
  exists in the PRD.)

This note reclassifies each check by what can already answer it — an
existing automated test, a new host-free or C++ test, an existing headless
harness — versus what is genuinely a pixel-level judgment that still needs
a human. Two rules apply throughout:

- A grep of a binding or a string constant is **not** a test: it proves the
  code was written, not that the path runs.
- `UI.Tests` dual-compiles only `UI/Logic/**` (ADR-0123). Anything living
  in `UI/ViewModels`, `UI/Services` or `UI/Config` is testable there only
  after its pure rule is extracted into `UI/Logic/`.

This is the third revision; the "Rejected suggestions" section at the end
records what two review passes proposed and was **not** adopted, with the
reason, so the same points are not re-raised.

## P.7 — Enhancements panel + Welcome/Continue cards

| Check | Source of truth today | Plan |
|---|---|---|
| Menu bar hidden in Player, shown in Advanced | Two sites set `IsMenuVisible`: the initializer in `MainWindowViewModel` (~line 99, `UiMode != Player && !AutoHideMenu`) and `MouseManager.UpdateMainMenuVisibility()`, which recomputes it on every mouse move (Player → early-return `false`; Advanced → exclusive-fullscreen / auto-hide / hover-band / menu-open logic) | **Extract one host-free helper** in `UI/Logic/` (e.g. `PlayerChrome.IsMenuVisible(uiMode, isExclusiveFullscreen, autoHide, menuOpen, cursorInBand)`) and make **both** call sites consume it, so the two cannot drift. Cover it in `UI.Tests`: Player is always hidden; Advanced follows the existing hover rule |
| SMS Overclock checkbox disabled-not-hidden | `PlayerEnhancementsToggle.SupportsOverclock` (host-free, tested) feeds `IsOverclockSupported`; `MainWindow.axaml` binds it to `IsEnabled` | Logic already covered. The `IsEnabled`-vs-`IsVisible` choice is a one-line code-review item, not a test |
| WideScrn/HiRes restore-not-clobber semantics | `UI.Tests/Config/PlayerEnhancementsToggleTests.cs` — 18 checks, green | **Already covered** |
| Welcome card shown once / Continue card when history exists | `ShouldShowWelcomeCard`/`ShouldShowContinueCard` unit-tested; XAML→screen wiring is not | Logic covered. Rendering: **manual** (see below) |
| HQ4x filter actually applied | `BaseVideoFilter::TakeScreenshot` runs `ScaleFilter::GetScaleFilter(...)->ApplyFilter` and scanlines before writing the PNG | **Headless-measurable**: `scripts/headless_record` with the `screenshot` flag, then check the PNG dimensions (4× native) and a filter signature by image processing |
| 16:9 stretch | Aspect ratio is viewport geometry in `VideoRenderer`, not part of the screenshot pipeline | **Manual** — a headless PNG never carries it |
| Welcome/Continue cards on screen | Avalonia controls in `MainWindow.axaml`; the C++ core does not know they exist | **Manual** until an in-process Avalonia test host exists (see Rejected) |

## P.6 — catalog update against a real fetch

| Check | Source of truth today | Plan |
|---|---|---|
| Correct trigger (`content_id`, no auto-downgrade) | `UI/Logic/CommunityCatalogUpdateDecision.cs` — 15 tests, green | Already covered |
| "Updated …" toast wording | **The PRD item is stale.** `UI/Services/CommunityPackInstallCoordinator.cs` (~line 212) handles the `Updated` verdict by clearing the folder and letting the reinstall proceed; the run then ends in the ordinary toast from `UI/Services/CommunityPackInstallService.cs` (~line 157), `Community pack '<name>' installed`. The locally-edited branch (ADR-0147) returns the `UpdateAvailable` outcome text instead. No separate "Updated" toast was ever implemented | **Close the pending item**: amend the PRD P.6 row to say the update path reuses the install toast (and the `UpdateAvailable` message when a local edit exists). No code change |
| End-to-end fetch against the real host | Real network round-trip to GitHub / MediaFire / Drive | **Shipped as an on-demand script**, never a build-blocking test: `scripts/catalog_update_live_check.sh <rom>` runs the F6.4b coordinator against a live catalog entry and reads the `[CommunityPackInstall] update verdict=…` log line. Rate limits and host outages make it unfit for CI. Its catalog phase (`--no-launch`) was run live on 2026-09-03 (HTTP 200, `roms/Zelda.nes` → catalog row #139); the client phase needs a logged-in desktop session, which the agent shell does not have |

## ADR-0142 — crossfade "click-free" check

### Finding: the shipped fade is block-stepped, not a ramp

`OggMixer::MixAudio` computes `fadeIn`/`fadeOut` **once per call** and
passes a single `uint8_t` volume to `OggReader::ApplySamples`, which
applies it to the whole block. `SoundMixer::PlayAudioBuffer` calls
`MixAudio` once per emulated frame (~735 samples at 44.1 kHz / 60 Hz).
With `kBgmFadeSamples = 1764` (`Core/NES/HdPacks/OggMixer.h:19`) the fade
is therefore 2–3 volume steps of roughly 40 % each — a quieter click, not
a crossfade. The contract in ADR-0142 ("no click at the boundary") is not
what the code does.

### Plan

1. **File it** on the bug board (`scripts/report-bug.sh`, P1) and amend
   ADR-0142's Consequences: the fix is per-sample linear interpolation
   inside the block (ramp `volume` from the block's start factor to its end
   factor in `ApplySamples`, or apply the ramp in `MixAudio` before
   handing a constant volume down). `kBgmFadeSamples` stays.
2. **Unblock unit testing**: `OggMixer`/`OggReader` call
   `_emu->IsRunAheadFrame()` on the concrete `Emulator`, and the
   `core-unit-tests` target in the makefile deliberately does not link
   `Emulator`. Inject the run-ahead probe (e.g. a `std::function<bool()>`
   or a tiny interface) so the mixer can be built without the emulator.
3. **C++ unit test in `scripts/core_unit_tests.cpp`** (same framework-free
   style as the existing cases), after 1 and 2:
   - feed two stub readers (or two short synthetic OGGs) with constant
     non-zero amplitude;
   - play A, switch to B, then `StopBgm`; mix in **735-sample blocks**,
     the real block size, and record the output;
   - assert within each fade window: no sample-to-sample jump larger than
     the two linear ramps can produce (derivable from `kBgmFadeSamples`,
     plus tolerance for the 8-bit volume quantisation); the mixed envelope
     tracks the expected curve (first-order continuity); silence after the
     stop window;
   - assert a run-ahead block does not advance the counters.

No listening, no ROM, no GUI. Constant-amplitude input avoids the false
positives a threshold detector would raise on percussive transients in
real music.

### Tooling correction (kept from the previous revision)

The F5.4g item 11 "extract-audio" tool (ADR-0135) extracts the game's APU
audio to build packs; it does not capture the `OggMixer` output.
`scripts/headless_record` records the first N seconds with no input, so a
music switch may never occur. Neither replaces the unit test above.

## F6.5 — end-to-end install with user-supplied audio

**Reclassified: stays a guided manual acceptance of the installer.**

- What F6.5 accepts is the **install flow** (ADR-0138 split distribution):
  the pending-dependency prompt for user-supplied audio, hash validation of
  the file dropped into `.cache/downloads/`, patch application when the
  recipe has one, and the `.mep-install.json` stamp. That flow lives in
  `UI/Services/CommunityPackInstallCoordinator.cs` and
  `CommunityPackInstallService.cs`, neither of which is dual-compiled into
  `UI.Tests`.
- `scripts/smoke_pack_headless.sh` is the **F6.6 load smoke**: it takes an
  already-installed folder, boots the real core, and requires the positive
  `[MEP] audio: … BGM / … SFX tracks` log line (failing on
  `OGG file not found`). It does not run the installer and its header
  explicitly excludes `<patch>`/`patches[]`. It is a **post-condition** of
  the F6.5 run, not a substitute for it.
- Plan: write a short checklist for the manual run (drop a user-supplied
  OGG, confirm the prompt, confirm the stamp and the mep/ folder), then run
  `smoke_pack_headless.sh` on the result as the objective "did it load"
  gate. Use a pack whose bundled `.ips`/`.bps` is *wired* (ADR-0148
  amending ADR-0144) so the patch + extraction path is the one exercised.
  **Written**: `docs/validation/f65-install-acceptance-checklist.md`, against Mega Man
  (USA) (issue #138 — its five bundled `.ips` were re-linted on 2026-09-03
  and all report `present, wired`). It also records a gap found while
  writing it: all 11 catalog rows are `kind: hd-legacy` with no `deps`, so
  no published row can raise the pending-dependency prompt today; the
  checklist reaches it through the fetcher's own ETag cache instead.
- Optional later: extract the coordinator's pure decisions (prompt list,
  hash-match verdict) into `UI/Logic/` and test them; that shrinks the
  manual checklist but does not remove the GUI step.

## What remains genuinely manual

- P.7: 16:9 stretch, Welcome/Continue cards on screen.
- F6.5: the installer's GUI flow with a user-supplied file.

Everything else is an existing test, a new unit test, or an on-demand
headless script.

*Updated 2026-09-03 by wave 2*: of the two above, the cards are now
asserted headlessly and the aspect-ratio math by a `core_unit_tests` case;
the F6.5 flow shrank to its OS file-picker step. See "What remains
genuinely manual after wave 2" at the end of this note for the current
list.

## Execution order and status

Steps 1-5 and 7 were executed on 2026-09-03 (four parallel workstreams);
step 6 is the only one that still needs a human at a display.

| # | Step | Status |
|---|---|---|
| 1 | **P.6**: amend the PRD row (toast pending item is stale). Zero code | **done** - the PRD P.6 row now records that no separate "Updated ..." toast exists nor is needed |
| 2 | **ADR-0142**: file the block-step bug, amend the ADR, fix the ramp, inject the run-ahead probe, add the `core_unit_tests` case | **done** - bug #151 (filed, fixed, closed); ADR-0142 Consequences amended; per-sample ramp in `Core/NES/HdPacks/OggFadeRamp.h` (16.16 fixed point) behind the new `IOggSource`; `OggMixer`/`OggReader` decoupled from `Emulator` via an injected run-ahead probe; `scripts/core_unit_tests.cpp` Bloco I, 192/192 cases pass, and reverting the ramp fails it (worst jump 1906 vs 6.27 allowed) |
| 3 | **P.7**: `PlayerChrome` helper in `UI/Logic/` consumed by both `MainWindowViewModel` and `MouseManager`, plus tests. HQ4x check via `headless_record` screenshot | **done** - `UI/Logic/PlayerChrome.cs` (`IsMenuVisible` + `IsCursorInMenuBand`) consumed by both call sites, 8 `UI.Tests` cases, 386 total green; `scripts/headless_record.cpp` gained a `filter=<name>` flag (it never pushed a `VideoConfig`, so no filter was reachable headlessly) and `scripts/check_hq4x_screenshot.sh` measures 256x240 -> 1024x960 with interpolated colours (11 -> 146 distinct) |
| 4 | **F6.5**: write the manual checklist; run it once with a wired-patch audio pack; gate the result with `smoke_pack_headless.sh` | **checklist written, run pending** - `docs/validation/f65-install-acceptance-checklist.md`. Gap found: all 11 published catalog rows are `kind: "hd-legacy"` with no `deps`/`recipe`, so no live row can raise the pending-dependency prompt; Part B therefore uses a seeded catalog |
| 5 | **P.6 real fetch**: on-demand script, log-line check | **script written, phase 1 verified live** - `scripts/catalog_update_live_check.sh`; phase 2 needs a logged-in desktop session and reports the headless-shell case instead of passing silently |
| 6 | **Manual screen pass** for 16:9 and the cards, last | **superseded by wave 2 (2026-09-03)** - the cards are asserted by `UI.HeadlessTests/PlayerHomeCardsTests.cs` and the aspect-ratio math by `core_unit_tests` Bloco N; only the on-window letterbox fit is still a human pass |
| 7 | Separately: an ADR proposing `Avalonia.Headless` for XAML wiring tests | **done** - ADR-0150, Status `proposed` (deliberately not accepted: an accepted ADR is a work request). **Accepted by the user on 2026-09-03** and implemented the same day as wave 2's `UI.HeadlessTests/` project |

## Rejected suggestions (and why)

Two review passes (2026-09-03) proposed the items below. They were not
adopted; the reason is recorded so they are not re-raised.

| Suggestion | Source | Why rejected |
|---|---|---|
| Keep "static grep of the binding / string constant" as the acceptance for P.7 menu and P.6 toast | plan v1 | A grep proves the code exists, not that the path runs. Replaced by extraction + `UI.Tests`, or by closing the item as stale |
| Test `IsMenuVisible` / `SupportsOverclock` reactivity "in the ViewModel via `UI.Tests`" | review 1 | Not possible as-is: `UI.Tests` compiles only `UI/Logic/**` (ADR-0123). The rule has to be extracted first, which is what the plan now does |
| Adopt `Avalonia.Headless` / `Avalonia.Headless.XUnit` as a step of this plan | review 1 | Right long-term answer for XAML wiring, but it changes unit-test/CI wiring, which CLAUDE.md routes through an ADR. Listed as a separate ADR proposal, not a plan step |
| Drive the real macOS window via Accessibility/AppleScript for screenshots | plan v1 | Unreliable for non-native Avalonia apps; setup cost outweighs the two remaining visual checks |
| Crossfade detector as "compare rendered signal against the expected post-interpolation curve, with FFT / phase-continuity checks" | review 1 | Over-engineered for a fade whose curve is a known linear constant. The unit test asserts the ramp directly against `kBgmFadeSamples`; no FFT needed |
| Export the crossfade WAV with the "extract-audio" tool and run a threshold script | plan v1 | Wrong tool (ADR-0135 extracts APU audio, not `OggMixer` output) and a threshold detector false-positives on real transients |
| Write the crossfade test so it passes against the current code by using `sampleCount = 1`, or by asserting block-sized steps as the contract | review 2 (offered as an alternative) | Would enshrine the defect. The ADR says "no click"; a 40 % step per block is a click. Fix the ramp, then test the ramp |
| Treat `scripts/smoke_pack_headless.sh` (plus a buffer-energy assertion) as the F6.5 acceptance | plan v2 / review 1 | It is the F6.6 load smoke of an already-installed folder; it never runs the installer or the dependency prompt. Kept only as a post-condition gate |
| Test the F6.5 installer with "a C# service test with local fixtures" | review 2 | Same ADR-0123 barrier: `UI/Services` is not dual-compiled. Feasible only after extracting the pure decisions into `UI/Logic/`, listed as optional later work |
| Verify F6.5 by comparing installed file hash/duration on disk | plan v1 | Proves the copy, not the install flow or the load |
| Assert "non-zero energy in the Core's sample buffer" as proof the audio played (F6.5) | review 1 | Useful but subordinate: the smoke's `[MEP] audio: … tracks` positive line plus the `OGG file not found` gate already catch registration failures; a decode failure after registration is a core bug, better caught by the `OggMixer` unit test |
| "Fix the file path `UI/Logic/CommunityPackInstallCoordinator.cs`" | review 2 | The plan never wrote that path; only the file name. The path `UI/Services/` is now spelled out to remove the ambiguity |
| Treat `MouseManager.UpdateMainMenuVisibility()` as *the* source of truth and the ViewModel line as irrelevant | review 2 | Overstated: in Player both sites yield the same `false`. Adopted in reduced form — one helper consumed by both sites so they cannot drift |
| Automate the real-fetch check as a regular test | plan v1 (implied) | External hosts, rate limits and outages make it non-deterministic; kept as an on-demand script |

## Wave 2 — the rest of the project's manual/pending items

The first wave covered four items (P.6 toast, P.7 menu + HQ4x, ADR-0142
crossfade, F6.5 checklist). A full sweep on 2026-09-03 of the PRD (Part A
and Part B), `docs/adr/*.md` with Status `accepted`, and the open issues on
the bug board found ~24 further "manual", "pending" or "not verified"
clauses. They are classified below by the *same* rule the first wave used:
what can a host-free unit test, a `core-unit-tests` case or an on-demand
headless script actually answer, versus what needs eyes or hardware.

Board state at the time of the sweep: the 11 open issues are all
`community-pack` intake rows; #149, #150 and #151 are closed. No open bug
is waiting on a validation.

### 2A. Automatable with the tools already in the repo

Wave 1 made several of these cheaper: decoupling `OggMixer`/`OggReader`
from the concrete `Emulator` (injected run-ahead probe + `IOggSource`) put
the whole replaced-BGM path inside the `core-unit-tests` target, and
`scripts/headless_record.cpp`'s new `filter=<name>` flag makes the
screenshot pipeline configurable from a script.

#### Wave 2 status 2026-09-03

All nine 2A items were executed on 2026-09-03, in the suggested order
below. Same shape as the wave-1 table: what the pending clause was, and
what now answers it.

| Item | Pending clause | Status |
|---|---|---|
| F5.4g Block C item 8 | "loop-intro não repete" (listening) | **done** - `scripts/core_unit_tests.cpp` **Bloco J** covers ADR-0134's loop-point rule through the new decoder-agnostic `Core/NES/HdPacks/OggLoopStream.h` (an `IOggDecoder` seam the production `OggReader` delegates to): consuming past the track end returns to `loopPosition`, not to 0, and a track without a loop point behaves exactly as before. Defect-probed - seeking to 0 instead fails 3 cases |
| F5.4g Block C item 9 | SMB1/Zelda SFX audible | **done** - the ADR-0133 mask is now the shared header `Core/Shared/Audio/ReplacementMuteMask.h` (`FullTonalMute`/`IsMuted`/`Compute(roles)`; a template, so the mixer never includes `ChannelRoleClassifier`, as ADR-0133 requires), consumed by `NesAudioFingerprint::UpdateReplacementMuteMask` and `NesSoundMixer::GetChannelOutput`. **Bloco K** asserts that exactly the fingerprinted channel is muted and that SFX / expansion / DMC channels are not. Defect-probed. The audible end-to-end (real game, real ears) is the residue |
| F5.4g Block B | "GUI/listening validation of the rendered audio" | **done** - **Bloco L** renders the `EnhancedSynthEngine` against the committed PCM golden `docs/specs/golden/synth/enhanced-synth-pcm.txt` (128 frames from a synthetic preset declared in the test, ±2 LSB tolerance plus a >1000 peak gate so a silent render cannot pass; cwd-relative golden per ADR-0129). Defect-probed - moving the harmony mix from 0.80 to 0.79 shifts 8 samples. Timbre judgement stays subjective; regression coverage no longer is |
| ADR-0120 §4 | the C++ E2E zip harness "does not exist"; zip/slip recipe kinds "that is a manual" | **done** - **Bloco M** drives the whole `PrepareZip` pipeline through the new `Core/Shared/EnhancementPacks/MepZipExtract.h` (stamp/cache reuse, stale-cache wipe, zip-slip plan validation, ADR-0120 fallback-subfolder resolution, extraction), which `MepPackManager::PrepareZip` now delegates to; an `IArchive` seam keeps the real archive readers out of the test link. Covers path traversal, absolute path (incl. a Windows drive letter), nested wrapper fallback, cache-stamp reuse, stale-cache wipe, a symlink left in the cache being wiped, the empty-archive guard and the `.mep-source` stamp. Defect-probed per check. Caveat recorded in ADR-0120 §4: miniz's writer cannot author a true `S_IFLNK` entry, so symlinks are covered by their two reachable halves (a path-payload entry writes as a plain file; a pre-existing cache symlink is wiped), not by a real symlink inside an archive |
| P.7 | 16:9 stretch | **done for the math** - the destination-size rule is extracted into `Core/Shared/Video/AspectRatioMath.h` and asserted by **Bloco N** per `VideoAspectRatio` setting (NoStretching/Auto/4:3/16:9/NTSC/PAL/Custom → the destination size; e.g. 240 rows → 256/320/427 columns). **Residue**: the on-window letterbox fit (`RendererPanel_LayoutUpdated` in `UI/Windows/MainWindow.axaml.cs`, `FullscreenForceIntegerScale`) is not in that header and stays untested geometry |
| P.4 | "Player cannot reach Debug without switching", Esc-while-playing | **done, and it was a real defect** - `UI/Logic/PlayerDebugAccess.cs` (`IsDebugReachable(UiMode)` + `IsDebugEntryEnabled`) is consumed by the new `ApplyPlayerDebugGate` in `UI/ViewModels/MainMenuViewModel.cs`, which sets every Debug action's `IsEnabled` *before* `DebugShortcutManager.RegisterActions`; `UI.Tests/Config/PlayerDebugAccessTests.cs` covers it. The old claim was false: hiding the menu only blocked the mouse, and the debugger hotkeys still fired in Player via `DebugShortcutManager`. Gating `IsEnabled` closes both paths in Player (what PRD §6 specifies) and is a strict no-op in Advanced. The Esc-while-playing keyboard-block exemption for `ToggleOverlay` is now `Core/Shared/ShortcutKeyRules.h` + **Bloco O** |
| F6.4b / F6.5 | "manual GUI pass"; the installer half of the F6.5 run | **done** - the coordinator's pure decisions are extracted: `UI/Logic/CommunityPackDepPlan.cs` (`Build(deps, alreadyResolvedIds, packFolderFiles, downloadsCacheFiles)` → Resolved/Pending, the hash verdict still delegated to the existing `CommunityPackDepResolver`) and `UI/Logic/PlayerDebugAccess.cs`, both consumed by `UI/Services/CommunityPackInstallCoordinator.cs`; `UI.Tests/CommunityPacks/CommunityPackDepPlanTests.cs` covers dep present/absent/partial, hash match/mismatch and a wrong-bytes-right-name negative control. **Residue**: the F6.5 run's manual surface is now only the OS file-picker step (a human choosing the user-supplied file) plus the OSD toast appearing |
| D13 / ADR-0148 rule 1 | "classify refusal is NOT yet confirmed — still needs one CI run" | **done, locally, no CI run** - the real `.github/ai/validate-classify.md` prompt driven by the real `scripts/validate_pack_local.sh --pack-file`/`--issue-body` over the purpose-built fixture `tests/fixtures/community-pack/adr0148-rule1-unlistable/`: a lint-valid (0 errors) pack whose `<bgm>`/`<sfx>` targets are absent and whose bundled `.ips` is unwired returns `verdict=invalid`, with a comment naming the three ways to make it listable. A prompt-injection variant (bundled README + patch file name + the issue's game field) did not change the verdict. The run added an offline mode to `validate_pack_local.sh` and fixed a pre-existing `ROOT`-shadowing bug in its `run_game()`. Recorded in ADR-0148 and in the PRD D13 row |
| ADR-0143 | "the split stays a manual step … automating it in the workflow is deferred" | **not a validation** - unchanged: deferred by decision, not by feasibility. The split logic is already in `scripts/`; wiring it into `community-pack-validate.yml` is a slice |

### 2B. Was blocked on the ADR-0150 decision — unblocked and done

Pure XAML wiring with no logic layer left to extract; the gating
predicates behind them were already unit-tested, so what was unverified is
strictly "is it on screen and does it react".

ADR-0150 was **accepted on 2026-09-03 and implemented the same day**: the
new `UI.HeadlessTests/` project (references `UI/UI.csproj` +
`Avalonia.Headless(.XUnit)`; `UI.Tests` stays host-free per ADR-0123, and
`NativeCore.cs` loads the real MesenCore when it is built and self-skips
otherwise, so the CI job stays honest per ADR-0131/0137), a
`make headless-ui-tests` target, and a separate `headless-ui-tests` job in
`.github/workflows/unit-tests.yml` (ubuntu-latest,
`-p:RuntimeIdentifier=linux-x64`; 4 run + 7 explicit skips when no core is
present). `UI.HeadlessTests/AGENTS.md` records the scope rule: wiring
only, never a rule `UI.Tests` could assert host-free. Two CI-critical
groups were defect-probed (making the tab reduction unconditional fails
`Advanced_settings_still_shows_every_tab`; renaming the highlight selector
fails `Pressed_binding_lights_the_button_up`). Cross-RID gotcha, recorded
in the ADR's consequences: building UI for another RID (e.g.
`dotnet build -p:RuntimeIdentifier=linux-x64`) and then running osx-arm64
without cleaning `UI/obj` yields CS8012 and a host crash ("No test is
available") — clean `UI/obj` between RID switches.

| Item | Status |
|---|---|
| P.7 — Welcome/Continue cards on screen | **done** - `UI.HeadlessTests/PlayerHomeCardsTests.cs`: the Welcome card is genuinely `IsOnScreen()` on a first Player boot, the Continue card on a populated recents list, and the Welcome CTA dismisses it for good. Found and fixed **issue #153** (an empty recents list collapsed the host, hiding the Welcome card); closed |
| P.4 §6 — Player Settings reduced tab set | **done** - `UI.HeadlessTests/PlayerSettingsTabsTests.cs` (the reduced set renders in Player; Advanced still shows every tab) |
| P.5 — keyboard-arrow navigation in the picker | **done** - `UI.HeadlessTests/PlayerPackPickerTests.cs` asserts focus really moves between choices on ArrowDown/ArrowUp. Found and fixed **issue #154** (`XYFocus.NavigationModes` was never set on the `PackPickerList` `ItemsControl`, so the arrows moved no focus); closed |
| I.2 — live highlight in `ControllerConfigWindow` | **XAML half done** - `UI.HeadlessTests/ControllerHighlightTests.cs`: a `KeyBindingButton` with `Highlighted = true` gains the `highlighted` class and the #3388CC/#55AAEE restyle, and releasing restores it. **Residue**: the polling half (`InputApi` + a physically pressed key) needs a real pad/keypress and stays hardware |
| I.3 — circularity ring in the Test tab | **markup done** - `UI.HeadlessTests/GamepadTestTabTests.cs`: selecting the Test tab realizes one section per pad, the deadzone ring and live dot take their size/offset from the view-model, and the circularity readout replaces its hint once measured. **Residue**: the physical pad end-to-end stays hardware |

### 2C. Genuinely not automatable here

| Item | Why |
|---|---|
| I.1, I.3 hardware items — pad GUI run, MBC7/GBA tilt UI, Linux `UpdateDevices()`, macOS pads without `extendedGamepad` | Needs the physical device and, for two of them, the other OS |
| P.5 "toast noise judgement", F5.4g timbre/listening quality | Subjective; a test can assert the toast fires, never that it is welcome |
| H7 / ADR-0128 GB/SMS cheat support, ADR-0004 v1-draft community review | Product decisions, not validations |
| F6.5 `LIVE_VALIDATION_ENABLED` → `'true'` | Deferred by explicit user decision 2026-08-29 |
| P.6 phase 2 of `catalog_update_live_check.sh` | Needs a logged-in desktop session; the script already detects and reports the headless-shell case instead of passing silently |
| ADR-0130 `.gitignore` exclusion for new harness binaries | A process rule for authors, not a runtime behaviour |

### Order followed by wave 2 (executed 2026-09-03)

1. F5.4g C item 8, then C item 9, then Block B — they reuse the Bloco I
   harness and close the oldest listening-pending clauses. **Done**
   (Blocos J, K, L).
2. ADR-0120 §4 zip fixtures. **Done** (Bloco M + `MepZipExtract.h`).
3. The two extractions (P.4 Debug/Esc gating, F6.4b/F6.5 coordinator
   decisions), both following `PlayerChrome`'s shape. **Done**
   (`PlayerDebugAccess.cs` + `ShortcutKeyRules.h`/Bloco O;
   `CommunityPackDepPlan.cs`).
4. P.7 viewport geometry, D13 local refusal fixture. **Done**
   (`AspectRatioMath.h`/Bloco N; the ADR-0148 rule-1 fixture).
5. ADR-0150: a human decision, which unblocks 2B as its own wave.
   **Accepted and implemented the same day** — 2B is done, see above.

### What remains genuinely manual after wave 2

- **16:9** — the on-window letterbox fit (`RendererPanel_LayoutUpdated`,
  `FullscreenForceIntegerScale`). The aspect-ratio math itself is Bloco N.
- **F6.5** — the OS file-picker step (a human choosing the user-supplied
  file) and the OSD toast appearing. Everything upstream of the picker is
  now host-free and unit-tested.
- **Hardware** — a physical pad or keypress: I.2's polling half, I.3's
  end-to-end, and the 2C items below.
- **Subjective audio** — timbre quality (F5.4g Block B), the audible
  SFX-during-OGG end-to-end (Block C item 9), the P.5 toast-noise
  judgement.
