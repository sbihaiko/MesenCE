# ADR-0150: Avalonia.Headless for XAML-wiring tests (Welcome/Continue cards, menu visibility, enhancements panel)

- Status: proposed
- Date: 2026-09-03
- Origin: `docs/manual-validation-automation-plan.md` (step 7 of "Proposed execution order"; the plan's "Rejected suggestions" table lists `Avalonia.Headless` as the right long-term answer for XAML wiring but explicitly refuses to adopt it as a plan step, because it changes unit-test/CI wiring and CLAUDE.md routes that through an ADR).
- Related: ADR-0123 (UI/Logic host-free firewall: the dual-compile is the authoritative gate), ADR-0130 (core unit-test binary gitignored), ADR-0131 (`unit-tests.yml` contract invariants), ADR-0137 (repo-hygiene checks wired into make/CI), PRD Part B §5–§6 (Player shell, pack picker, enhancements quick-toggle panel).
- Decides nothing yet: this ADR asks for a human choice between adopting a headless Avalonia test host and keeping the current manual pass.

## Context

`UI.Tests/UI.Tests.csproj` is deliberately host-free (ADR-0123): no
`RuntimeIdentifier`, no `ProjectReference` to `UI/UI.csproj`, no Avalonia
package. It dual-compiles exactly three things —
`../UI/Logic/**/*.cs`, `../UI/Interop/InteropEnums.cs`, and its own tests —
so an accidental `Avalonia`/`EmuApi` dependency fails `dotnet test` on any
OS with no SDL2 and no `MesenCore` native library present. `make unit-tests`
and the `ui-tests` job of `.github/workflows/unit-tests.yml` both run that
one project (preceded by `scripts/verify-ui-logic-firewall.sh`) on a plain
`ubuntu-latest` runner.

That boundary buys cheap, portable tests and it is why every recent Player
shell rule was written as a host-free helper: `PlayerEnhancementsToggle`,
`PlayerPackPicker`, `UiModeDefaultRule`, `PackPreferenceResolver`,
`CommunityCatalogUpdateDecision`. All of them are covered.

What is **not** covered is the step after the rule: whether the XAML
actually consumes it. Concretely:

- **Welcome/Continue cards** — `ShouldShowWelcomeCard` /
  `ShouldShowContinueCard` are unit-tested; that the cards in
  `MainWindow.axaml` are bound to them, are in the visual tree, and become
  visible/collapsed accordingly is verified only by a human looking at a
  real window.
- **Menu visibility in Player vs Advanced** — the plan's P.7 row extracts
  one `PlayerChrome.IsMenuVisible(...)` helper consumed by both
  `MainWindowViewModel` and `MouseManager.UpdateMainMenuVisibility()`. The
  helper will be tested; that `IsMenuVisible` reaches the menu bar's
  `IsVisible` is not.
- **Enhancements quick-toggle panel** — `SupportsOverclock` is tested; that
  the SMS Overclock checkbox binds it to `IsEnabled` (disabled, not hidden)
  is described in the plan as "a one-line code-review item, not a test",
  which is an accurate statement of today's tooling, not of what is
  desirable.

A grep for the binding string is not a test (the plan's first standing
rule): it proves the markup was written, not that the path runs. The
consequence is that PRD Part B items keep landing with "manual" in their
Acceptance column, and every future edit to `MainWindow.axaml` re-opens
checks that were already passed by hand once.

`Avalonia.Headless` (and `Avalonia.Headless.XUnit`, which supplies
`[AvaloniaFact]`/`[AvaloniaTheory]` and a UI-thread dispatcher) runs a real
Avalonia application with a null windowing/rendering backend, in-process,
under `dotnet test`. Controls are instantiated, styles applied, bindings
evaluated and the visual tree walked, with no display server. The app
already targets Avalonia 12.1.1 (`UI/UI.csproj`), for which the headless
packages exist at the matching version.

The blocker is not the library, it is the wiring. Testing `MainWindow.axaml`
means referencing the assembly that contains it, and `UI/UI.csproj` is the
assembly that also contains `UI/Interop/EmuApi.cs` — ~60 `DllImport`s
against `MesenCore`. A `ProjectReference` to it therefore drags the native
build, the desktop Avalonia stack and the platform RID into a job whose
entire value today is that it needs none of them. That is a change to the
unit-test and CI wiring, which is exactly the class of decision CLAUDE.md
says goes through an ADR rather than being done in passing.

## Proposed decision (not decided)

Adopt a **second, separate** test project — call it `UI.HeadlessTests` —
rather than adding Avalonia to `UI.Tests`:

1. **`UI.Tests` is untouched.** Its csproj keeps no Avalonia package, no
   `ProjectReference` and no `RuntimeIdentifier`; ADR-0123's dual-compile
   stays the authoritative host-free gate and
   `scripts/verify-ui-logic-firewall.sh` keeps scanning the same set. The
   firewall's guarantee is not weakened by anything below.
2. **`UI.HeadlessTests/UI.HeadlessTests.csproj`** references
   `Avalonia.Headless` + `Avalonia.Headless.XUnit` at the app's Avalonia
   version and `ProjectReference`s `UI/UI.csproj`. Its scope is *wiring*
   only: instantiate a control or window, set the view-model properties the
   host-free rule would produce, and assert on the visual tree
   (`IsVisible`, `IsEnabled`, presence of the named card). It never asserts
   a rule that `UI.Tests` can assert host-free — duplicating the rule there
   would put the logic behind an Avalonia dependency for no gain.
3. **P/Invoke containment.** The tests must not call `EmuApi`. Whether a
   headless `MainWindow` can be constructed without the native library
   loading is the open feasibility question (§"Unknowns"); the fallback is
   to test the smaller `UserControl`s (the enhancements panel, the
   Welcome/Continue cards) in isolation instead of the whole window, which
   covers the three checks named above without booting the shell.
4. **Wiring.** A new `make headless-ui-tests` target, and a **separate job**
   in `.github/workflows/unit-tests.yml` — not a step appended to
   `ui-tests`, so a headless-host failure never reds the cheap host-free
   leg and ADR-0131's contract invariants for that job stay readable. The
   job installs .NET and, if the reference forces it, builds or stubs the
   native library; if it cannot run without a real `MesenCore` build, it is
   `continue-on-error: false` but gated to the platforms that already build
   it, and this ADR must say so explicitly before it is accepted.
5. **Scope cap.** Headless tests cover binding/visibility wiring. They do
   **not** replace the two checks the plan classifies as genuinely visual —
   16:9 stretch (viewport geometry in `VideoRenderer`, not in the Avalonia
   tree) and the F6.5 installer GUI flow.

### Unknowns to resolve before this can be accepted

- Whether `MainWindow`/`MainWindowViewModel` can be constructed under the
  headless backend without `MesenCore` being loadable, or whether only
  leaf controls are reachable. This decides whether item 3's fallback is
  the main path.
- Whether the CI job can stay on `ubuntu-latest` without a native build, or
  becomes a matrix leg attached to an existing build job.
- Whether AOT/trim parity (`IsAotCompatible`, the
  `JsonSerializerIsReflectionEnabledByDefault=false` line `UI.Tests`
  carries) is meaningful for a project that references the app rather than
  dual-compiling it.

A spike answering the first two, on a throwaway branch, is the cheapest way
to make this ADR decidable.

## Consequences

If adopted:

- Welcome/Continue cards, menu visibility and the enhancements panel move
  from "manual GUI pass" to an assertion that runs on every push, and the
  PRD Part B rows citing them can name a test instead of a human.
- Future `MainWindow.axaml` edits get a regression net; the recurring
  "manual GUI run pending" note in the memory of P.4/P.5/P.7 stops
  accumulating.
- Cost: a second test project to keep at Avalonia-version parity with
  `UI/UI.csproj` (a version bump now touches two files), a CI job that is
  materially more expensive than the existing host-free one, and a
  `ProjectReference` that couples test runtime to the native library's
  build state.
- Risk: a headless job that is flaky or that needs `MesenCore` present will
  be muted rather than fixed, which is worse than the honest manual pass —
  ADR-0137's "a documented-but-unrun guardrail is worse than none" applies
  unchanged here.
- Ongoing pressure to write new rules directly against the visual tree
  instead of extracting them into `UI/Logic/`. The §2 scope rule
  ("wiring only, never the rule") is the mitigation and would need
  restating in `UI.Tests/AGENTS.md` and the new project's `AGENTS.md`.

If not adopted, the status quo is unchanged and explicit: those three
checks stay in a written manual checklist, re-run on each release rather
than each push.

## Alternatives considered

- **Status quo — manual GUI pass** (the plan's step 6). Zero cost, zero
  wiring, and honest about what is verified. It does not scale: the same
  three checks are re-run by hand after every shell change, and nothing
  catches a binding deleted in an unrelated refactor. This is the real
  fallback if the spike above shows the headless host cannot run without a
  native build.
- **Drive the real macOS window via Accessibility/AppleScript** and
  screenshot it. Rejected in `docs/manual-validation-automation-plan.md`:
  Avalonia does not expose native AppKit control hierarchies, so element
  targeting is unreliable for a non-native toolkit, and the setup cost
  outweighs two remaining visual checks. It is also macOS-only, while CI is
  Linux.
- **Add Avalonia.Headless to `UI.Tests` itself.** Rejected: it would put an
  Avalonia package reference and a `ProjectReference` to `UI/UI.csproj`
  into the very project whose absence of both is ADR-0123's guarantee, and
  `verify-ui-logic-firewall.sh` checks for exactly those two markers.
- **Extract more into `UI/Logic/` and accept that markup is untested.**
  Already the working practice and worth continuing regardless — but it
  cannot reach the question this ADR is about, since the untested step is
  by definition the one that crosses from logic into XAML.
- **Screenshot comparison via the headless backend's frame capture.**
  Possible once a headless host exists, but a pixel baseline is brittle
  across themes, fonts and Avalonia versions. Out of scope here; visibility
  and enabled-state assertions are what the three checks need.
