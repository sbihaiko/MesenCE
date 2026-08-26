# UI/

## Purpose

.NET (Avalonia) desktop UI application — windows, ViewModels, config, and
the native interop bridge to Core via `EmuApi`. `UI/Logic/` is a carved-out,
host-free subset consumed by `UI.Tests` (Fase 0/1,
`docs/roadmap/plano-testes-unitarios.md`).

## Ownership

The main UI/ViewModel codebase is owned by the application as a whole.
`UI/Logic/` specifically is owned by the `plano-testes-unitarios.md`
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

## Work Guidance

- New host-free helpers extracted from ViewModels go under `UI/Logic/`,
  paired with tests under the matching `UI.Tests/<Area>/` subfolder.
- Never add an `Avalonia` or `EmuApi` reference to a file under
  `UI/Logic/` — if a helper needs a UI-side type (an enum, etc.), move
  that type out of its Avalonia-tainted file first (see Fase 2 of the plan
  for the `ConsoleType`/`CheatType` precedent).

## Verification

- `dotnet test UI.Tests/UI.Tests.csproj --nologo`

## Child DOX Index

(none — `Logic/` is a convention-only subfolder, not a separately
governed subtree)
