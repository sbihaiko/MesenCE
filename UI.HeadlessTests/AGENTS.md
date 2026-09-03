# AGENTS.md — UI.HeadlessTests

Headless Avalonia XAML-wiring tests (ADR-0150, accepted 2026-09-03). This
project is the deliberate opposite of `UI.Tests`.

## What this project is for

Instantiate the app's real windows/views under `Avalonia.Headless` (null
windowing + software render, no display server) and assert on the realized
visual tree: a named card is on screen, a tab is hidden, focus moves on a
key press, a style class restyles a control. It covers the step that no
host-free test can: the crossing from a rule into XAML.

## The firewall (do not blur this)

- `UI.Tests` dual-compiles `UI/Logic/**` and is host-free (ADR-0123): no
  Avalonia package, no `ProjectReference`, no `RuntimeIdentifier`. Its
  guarantee must stay intact.
- This project **does** reference `UI/UI.csproj`. The two are separate on
  purpose and must never be merged.
- **Scope rule: wiring only.** Assert `IsVisible`/`IsEnabled`/focus/
  bindings/presence on the visual tree. NEVER write a rule assertion here
  that `UI.Tests` can make host-free — that would put the logic behind an
  Avalonia dependency for no gain. New rules go into `UI/Logic/` first,
  where `UI.Tests` asserts them; this project only checks the wiring.
- The rules themselves are already covered host-free. If a test here is
  the *only* thing asserting a decision, it is in the wrong project.

## Native core containment

`MainWindow`'s constructor calls `EmuApi.InitDll()` before its XAML loads,
and some views call into the native `MesenCore` on construction or focus.
This project does **not** fake the core (a stub would answer with values
the real core never returns). Instead `NativeCore.cs` loads the REAL
library when this checkout has one built and, when it does not, the
affected tests skip with an explicit reason via `Assert.SkipWhen`.

`unit-tests.yml` never builds `MesenCore` (ADR-0131), so on CI only the
core-free wiring tests run (`PlayerSettingsTabsTests`,
`ControllerHighlightTests`) and the rest self-skip. That is the intended
posture — a documented skip is not a muted failure. Run `make core` and
then `make headless-ui-tests` locally to exercise every case.

## Running

```sh
make core             # once, so NativeCore finds a built library
make headless-ui-tests
# or, to reproduce the CI runner's "no core" state:
MESEN_CORE_LIB=none dotnet test UI.HeadlessTests/UI.HeadlessTests.csproj \
  -p:RuntimeIdentifier=$(MESENPLATFORM) --nologo
```

`UI/UI.csproj` hardcodes `<RuntimeIdentifier>win-x64</RuntimeIdentifier>`;
override it with `-p:RuntimeIdentifier=<rid>` (the makefile does this via
`$(MESENPLATFORM)`). `DefineConstants=TRACE` (DEBUG off) matters:
`App.Initialize()` attaches Avalonia developer tools under `#if DEBUG`, and
headless builds a fresh `Application` per test — the second attach throws.

## Test hygiene

- A headless test must detect the defect it targets. If it would pass
  without the XAML under test, it is a property-getter assertion in
  disguise — strengthen it or delete it.
- Prefer `IsEffectivelyVisible`/`IsOnScreen()` over `IsVisible` when the
  assertion is about the user seeing something: `IsVisible` is a local flag
  and a collapsed parent hides a control with `IsVisible=true`.
- `MainWindow.axaml` changes that only add `x:Name`/automation ids so a
  test can find a control are acceptable here; a change that alters layout
  or behaviour to satisfy a test is not.
