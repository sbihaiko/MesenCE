# UI/

## Purpose

.NET (Avalonia) desktop UI application — windows, ViewModels, config, and
the native interop bridge to Core via `EmuApi`. `UI/Logic/` is a carved-out,
host-free subset consumed by `UI.Tests` (delivered in Fase 0/1 of the
now-completed unit-test plan — see git history for
`docs/roadmap/plano-testes-unitarios.md`).

## Ownership

The main UI/ViewModel codebase is owned by the application as a whole.
`UI/Logic/` specifically is owned by the completed unit-test
test-infrastructure effort: it exists so ViewModel parsing/validation logic
can be exercised by real xunit tests without Avalonia or the native
`MesenCore` library.

## Local Contracts

- Every file under `UI/Logic/*.cs` must stay free of `Avalonia` and
  `EmuApi` references — BCL (plus `System.IO.Compression` where needed)
  only. This is what lets `UI.Tests/UI.Tests.csproj` dual-compile the same
  files (via `<Compile Include>`, no `ProjectReference` to `UI.csproj`), so
  any accidental UI/native dependency breaks `dotnet test` immediately
  rather than only being caught in review (see `UI.Tests/AGENTS.md`).
- `UI/Logic/*.cs` types return plain, host-free records/DTOs — never
  `ViewModelBase`/`ObservableObject` subtypes. The owning ViewModel maps
  the result into its UI-facing type (e.g. `MepPackListEntry` →
  `MepPackEntry`).
- `MepPackListParser.Parse(string)` mirrors `EmuApi.GetMepPackList()`'s TSV
  contract exactly: newline-separated rows; a `!`-prefixed row is a
  rejection message (leading `!` stripped, accumulated into
  `MepPackListResult.RejectedInfo`); an 8-column tab-separated row maps to
  a `MepPackListEntry` (origin `2`/`1`/other → `sibling`/`zip`/`folder`);
  any row with fewer than 8 columns is silently ignored. The `Sections`
  field is passed through raw — the `","` → `", "` display formatting
  stays in the ViewModel, not in this parser.

- **New ViewModels** (Fase 3 of the plan — applied opportunistically, "no
  código que tocarmos", not as a retrofit of existing VMs): a *new*
  ViewModel's constructor must not call `EmuApi`/`ConfigManager` I/O
  directly — data comes in via a method parameter (e.g.
  `Refresh(string packListText, string sha1, string sibling)`). This is
  data injection, not mocking `EmuApi` — no DI container, no
  `Avalonia.Headless`, no ViewModel/UI-click testing (all explicitly out of
  scope). Dialogs (`FileDialogHelper`, `MesenMsgBox`) stay in the
  `*.axaml.cs` code-behind, as `EnhancementPacksWindow` already does for
  OK/Install. Branching logic (parse, validate, classify) is born in
  `UI/Logic/` with a test in the same PR — never inlined in the VM. A
  `RelayCommand` is not required; a thin code-behind calling a plain VM
  method stays acceptable. `EnhancementPacksViewModel` itself is NOT
  retrofitted to this shape (it still calls `EmuApi`/`ConfigManager` from
  its constructor/`Refresh`) — only its parse/validate logic was extracted
  (Fase 1); a ctor taking `EnhancementPackConfig` + a Window-fed `Refresh`
  is optional future work, only if an orchestration test justifies it.

- **`UI.Tests.csproj` is NOT a member of `Mesen.sln`.** Including it would
  expose the project to the solution-level flows in
  `.github/workflows/build.yml`/`tests.yml`
  (`dotnet restore -r win-x64 -p:PublishAot=true Mesen.sln`, Windows-only)
  and `dotnet-format-check.yml`
  (`dotnet format --verify-no-changes` against the whole `.sln`). This
  actor's environment is macOS/Linux, so the plan's own risk item —
  verifying locally that a RID-less `UI.Tests.csproj` survives that
  win-x64/AOT restore — cannot be executed here; per the plan
  ("Fase 0 — Mesen.sln"), the fallback when that can't be confirmed is to
  keep the project OUT of the `.sln` and let `.github/workflows/unit-tests.yml`
  invoke `UI.Tests/UI.Tests.csproj` directly instead. That is the choice
  recorded here. Consequence: `UI.Tests` code is not gated by
  `dotnet-format-check.yml` — if it later joins the `.sln`, either confirm
  the win-x64/AOT restore survives first, or add it with `Build.0` disabled
  under `Release|x64`, and its code must then also satisfy the repo's
  `.editorconfig` (tabs) under `dotnet format`. See `.github/AGENTS.md` for
  how the CI split reflects this.

## Work Guidance

- New host-free helpers extracted from ViewModels go under `UI/Logic/`,
  paired with tests under the matching `UI.Tests/<Area>/` subfolder.
- Never add an `Avalonia` or `EmuApi` reference to a file under
  `UI/Logic/` — if a helper needs a UI-side type (an enum, etc.), move
  that type out of its Avalonia-tainted file first (see Fase 2 of the plan
  for the `ConsoleType`/`CheatType` precedent).
- Apply the Fase 3 VM rule above (Local Contracts) when authoring a new
  ViewModel; do not retrofit it onto existing ones outside of files already
  being touched for another reason.

## Verification

- `dotnet test UI.Tests/UI.Tests.csproj --nologo`
- `./scripts/verify-ui-logic-firewall.sh`

## Child DOX Index

(none — `Logic/` is a convention-only subfolder, not a separately
governed subtree)
