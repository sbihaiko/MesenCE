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
  **Written**: `docs/f65-install-acceptance-checklist.md`, against Mega Man
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

## Execution order and status

Steps 1-5 and 7 were executed on 2026-09-03 (four parallel workstreams);
step 6 is the only one that still needs a human at a display.

| # | Step | Status |
|---|---|---|
| 1 | **P.6**: amend the PRD row (toast pending item is stale). Zero code | **done** - the PRD P.6 row now records that no separate "Updated ..." toast exists nor is needed |
| 2 | **ADR-0142**: file the block-step bug, amend the ADR, fix the ramp, inject the run-ahead probe, add the `core_unit_tests` case | **done** - bug #151 (filed, fixed, closed); ADR-0142 Consequences amended; per-sample ramp in `Core/NES/HdPacks/OggFadeRamp.h` (16.16 fixed point) behind the new `IOggSource`; `OggMixer`/`OggReader` decoupled from `Emulator` via an injected run-ahead probe; `scripts/core_unit_tests.cpp` Bloco I, 192/192 cases pass, and reverting the ramp fails it (worst jump 1906 vs 6.27 allowed) |
| 3 | **P.7**: `PlayerChrome` helper in `UI/Logic/` consumed by both `MainWindowViewModel` and `MouseManager`, plus tests. HQ4x check via `headless_record` screenshot | **done** - `UI/Logic/PlayerChrome.cs` (`IsMenuVisible` + `IsCursorInMenuBand`) consumed by both call sites, 8 `UI.Tests` cases, 386 total green; `scripts/headless_record.cpp` gained a `filter=<name>` flag (it never pushed a `VideoConfig`, so no filter was reachable headlessly) and `scripts/check_hq4x_screenshot.sh` measures 256x240 -> 1024x960 with interpolated colours (11 -> 146 distinct) |
| 4 | **F6.5**: write the manual checklist; run it once with a wired-patch audio pack; gate the result with `smoke_pack_headless.sh` | **checklist written, run pending** - `docs/f65-install-acceptance-checklist.md`. Gap found: all 11 published catalog rows are `kind: "hd-legacy"` with no `deps`/`recipe`, so no live row can raise the pending-dependency prompt; Part B therefore uses a seeded catalog |
| 5 | **P.6 real fetch**: on-demand script, log-line check | **script written, phase 1 verified live** - `scripts/catalog_update_live_check.sh`; phase 2 needs a logged-in desktop session and reports the headless-shell case instead of passing silently |
| 6 | **Manual screen pass** for 16:9 and the cards, last | **pending (human)** - the only genuinely pixel-level items left |
| 7 | Separately: an ADR proposing `Avalonia.Headless` for XAML wiring tests | **done** - ADR-0150, Status `proposed` (deliberately not accepted: an accepted ADR is a work request) |

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

| Item | Pending clause | Mechanism |
|---|---|---|
| F5.4g Block C item 8 | "loop-intro não repete" (listening) | `core_unit_tests` case reusing the Bloco I stub-source harness: consume past the track end and assert the read position returns to `loopPosition`, not to 0 (ADR-0134's contract) |
| F5.4g Block C item 9 | SMB1/Zelda SFX audible | `NesSoundMixer::SetReplacementMuteMask` (ADR-0133) and `NesAudioFingerprint` are not in the `core-unit-tests` source list; add them with the same dependency-injection move used on the mixer, then assert the mask mutes exactly the fingerprinted channel |
| F5.4g Block B | "GUI/listening validation of the rendered audio" | `EnhancedSynthEngine` is already in the target: render a fixed APU state to a PCM golden and diff it. Catches regressions, does not judge timbre — the subjective half stays manual |
| ADR-0120 §4 | the C++ E2E zip harness "does not exist"; zip/slip recipe kinds "that is a manual" | `MepRecipeOps` is already in the target; the gap is fixtures. Build zips with `Utilities/miniz.cpp` in the test itself (traversal, absolute path, symlink, nested wrapper) and assert the extraction refuses them |
| P.7 | 16:9 stretch | Extract the destination-rectangle math out of `Core/Shared/Video/VideoRenderer.cpp` into a pure function and test it per aspect-ratio setting. This tests the geometry, **not** the pixels on screen — the visual pass stays in "genuinely manual" below |
| P.4 | "Player cannot reach Debug without switching", Esc-while-playing | Same extraction pattern as `UI/Logic/PlayerChrome.cs`: move the Player menu/Debug gating predicate into `UI/Logic/`, consumed by the ViewModel. The Esc keyboard-block exemption lives in `Core/Shared/ShortcutKeyHandler.cpp` and needs that file added to the target |
| F6.4b / F6.5 | "manual GUI pass"; the installer half of the F6.5 run | The "optional later" already noted above: extract the coordinator's pure decisions (dependency prompt list, hash-match verdict) from `UI/Services/CommunityPackInstallCoordinator.cs` into `UI/Logic/`. Shrinks the checklist to the file-picker step; does not remove it |
| D13 / ADR-0148 rule 1 | "classify refusal is NOT yet confirmed — still needs one CI run" | Run it locally instead: `scripts/validate_pack_local.sh` with the `.github/ai/validate-classify.md` prompt family against a purpose-built refusal fixture. No CI run, no live host |
| ADR-0143 | "the split stays a manual step … automating it in the workflow is deferred" | Deferred by decision, not by feasibility — the split logic is already in `scripts/`. Wiring it into `community-pack-validate.yml` is a slice, not a validation |

### 2B. Blocked on the ADR-0150 decision

Pure XAML wiring with no logic layer left to extract; the gating
predicates behind them are already unit-tested, so what is unverified is
strictly "is it on screen and does it react".

- P.7 — Welcome/Continue cards on screen.
- P.4 §6 — the Player Settings reduced tab set rendering.
- P.5 — keyboard-arrows-as-gamepad-proxy navigation in the picker.
- I.2 — the live highlight in `ControllerConfigWindow`.
- I.3 — the circularity ring drawing in the Test tab.

While ADR-0150 stays `proposed`, all five stay manual. Accepting it is the
single change that would move this whole group into `UI.Tests`-shaped
coverage; per CLAUDE.md, accepting it is also a work request, so it needs
a human decision first.

### 2C. Genuinely not automatable here

| Item | Why |
|---|---|
| I.1, I.3 hardware items — pad GUI run, MBC7/GBA tilt UI, Linux `UpdateDevices()`, macOS pads without `extendedGamepad` | Needs the physical device and, for two of them, the other OS |
| P.5 "toast noise judgement", F5.4g timbre/listening quality | Subjective; a test can assert the toast fires, never that it is welcome |
| H7 / ADR-0128 GB/SMS cheat support, ADR-0004 v1-draft community review | Product decisions, not validations |
| F6.5 `LIVE_VALIDATION_ENABLED` → `'true'` | Deferred by explicit user decision 2026-08-29 |
| P.6 phase 2 of `catalog_update_live_check.sh` | Needs a logged-in desktop session; the script already detects and reports the headless-shell case instead of passing silently |
| ADR-0130 `.gitignore` exclusion for new harness binaries | A process rule for authors, not a runtime behaviour |

### Suggested order for wave 2

1. F5.4g C item 8, then C item 9, then Block B — they reuse the Bloco I
   harness and close the oldest listening-pending clauses.
2. ADR-0120 §4 zip fixtures.
3. The two extractions (P.4 Debug/Esc gating, F6.4b/F6.5 coordinator
   decisions), both following `PlayerChrome`'s shape.
4. P.7 viewport geometry, D13 local refusal fixture.
5. ADR-0150: a human decision, which unblocks 2B as its own wave.
