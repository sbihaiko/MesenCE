# UI.Tests/

## Purpose

xunit test project for the "host-free logic" carved out of the Avalonia UI
under `UI/Logic/` (docs/roadmap/plano-testes-unitarios.md, Fase 0/1). Exists
so `dotnet test` can run without SDL2, the native `MesenCore` shared library,
or Avalonia being present — on any OS, in CI or locally.

## Ownership

Owned by this test-infrastructure effort (`plano-testes-unitarios.md`). Not
part of the shipped application; excluded from `Mesen.sln`'s Windows-only
AOT/publish flow (see `.github/AGENTS.md` for the CI split).

## Local Contracts

- `UI.Tests.csproj`:
  - `TargetFramework` net10.0, no `RuntimeIdentifier`, no `ProjectReference`
    to `UI/UI.csproj`. Adding either turns this project into the full app
    build (SDL2/native dependency, Windows-only publish flags) and breaks
    the "cheap, cross-platform `dotnet test`" contract this project exists
    for.
  - `EnableDefaultCompileItems=false` with three explicit `<Compile Include>`
    entries: this project's own `**/*.cs`, `../UI/Logic/**/*.cs`, and the
    single file `../UI/Interop/InteropEnums.cs`. The `UI/Logic/` glob
    dual-compiles that folder into this assembly instead of referencing
    `UI.csproj` — any file under `UI/Logic/` that accidentally pulls in
    `Avalonia`/`EmuApi` fails `dotnet test` immediately. The `InteropEnums.cs`
    include is a single named file, not a folder glob, because it is the
    only host-free file inside the otherwise Avalonia/EmuApi-tainted
    `UI/Interop/` (it holds the `ConsoleType`/`CheatType` enums moved out of
    `EmuApi.cs`, Fase 2 of `docs/roadmap/plano-testes-unitarios.md`) — a
    folder glob there would risk pulling in an Avalonia-tainted file later.
- Every `UI/Logic/*.cs` file must stay free of `Avalonia` and `EmuApi`
  references (BCL + `System.IO.Compression` only) — that constraint lives in
  `UI/AGENTS.md` (nearest owner of `UI/Logic/`) but is enforced here by the
  dual-compile.
- Test classes are plain xunit `[Fact]`/`[Theory]`; no mocking framework, no
  DI container, no `Avalonia.Headless` — per the plan, ViewModel/UI-click
  testing is explicitly out of scope for this project.

## Work Guidance

- Add new test files under a subfolder matching the `UI/Logic/` area they
  cover (e.g. `UI.Tests/Mep/` for `UI/Logic/Mep*.cs`).
- Never add a `PackageReference` to Avalonia, or a `ProjectReference` to
  `UI/UI.csproj` — that reintroduces the native/SDL2 dependency this project
  is built to avoid.

## Verification

- `dotnet test UI.Tests/UI.Tests.csproj --nologo` — must run and pass with
  no SDL2/MesenCore/Avalonia on the machine.
- `make unit-tests` (repo root) runs the same command.

## Child DOX Index

(none — leaf directory)
