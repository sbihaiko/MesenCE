# ADR-0122: UI.Tests.csproj stays out of Mesen.sln; CI invokes the csproj directly

- Status: accepted (record of fact — already reflected in the repo; consolidates ADR-0053..0054, 0060, 0065, 0066)
- Date: 2026-08-27
- Consolidates: ADR-0053, ADR-0054, ADR-0060, ADR-0065, ADR-0066 (the sln half; the public-surface half is ADR-0125)

## Context
`UI.Tests/UI.Tests.csproj` is the host-free xunit project (net10.0, no
`RuntimeIdentifier`, no `ProjectReference` to `UI/UI.csproj`,
`EnableDefaultCompileItems=false` with explicit `<Compile Include>` entries for
`../UI/Logic/**/*.cs` and `../UI/Interop/InteropEnums.cs`). The question raised
four separate times during the unit-test plan (spec, decompose, Execute/T5,
auditor-b) was whether that project should join `Mesen.sln`. Membership would
expose it to the Windows-only solution-level flows: `dotnet restore -r win-x64
-p:PublishAot=true` in `.github/workflows/build.yml` / `tests.yml`, and
`dotnet format --verify-no-changes` in `.github/workflows/dotnet-format-check.yml`
(which runs `dotnet restore` + `dotnet format` at the repo root, so it resolves
the `.sln`). Whether a RID-less csproj survives that win-x64/AOT restore could
not be verified from the macOS/Linux actor environment.

Current state at HEAD: `grep -c UI.Tests Mesen.sln` returns 0; the rationale is
recorded in `UI/AGENTS.md` (Local Contracts, "`UI.Tests.csproj` is NOT a member
of `Mesen.sln`"), and `.github/workflows/unit-tests.yml` runs
`dotnet test UI.Tests/UI.Tests.csproj --nologo` on `ubuntu-latest`, so sln
membership is not needed for CI. ADR-0060 and ADR-0066 asked for exactly this:
promote the `UI/AGENTS.md` paragraph to a numbered ADR because the repo keeps a
real ADR register (`docs/adr/`) and `UI/Logic/MepZipValidator.cs` already
cites ADR-0049, so a durable cross-cutting trade-off living only in a directory
`AGENTS.md` was inconsistent.

## Decision
Keep `UI.Tests/UI.Tests.csproj` out of `Mesen.sln`. CI and local developers
invoke the csproj path directly (`dotnet test UI.Tests/UI.Tests.csproj`, wrapped
by `make unit-tests`, makefile target `unit-tests`). The test project therefore
never enters the Windows solution-level restore/publish/format paths.

Revisit trigger (explicit): only if a future consumer needs solution-wide
discovery, or once a Windows runner confirms that the RID-less csproj survives
`dotnet restore -r win-x64 -p:PublishAot=true`. If it is then added, add it with
`Build.0` disabled for `Release|x64` and bring `UI.Tests/**` into conformance
with the repo `.editorconfig` (tabs) so `dotnet format --verify-no-changes`
stays green.

## Consequences
- `UI.Tests/**` code (and the test-side compile of `UI/Logic/**`) is not
  gated by `dotnet-format-check.yml`; formatting of test code is review-only.
  This is a known, accepted gap, not an oversight.
- The RID-less-csproj-under-AOT-restore risk is deferred, not resolved; the
  revisit trigger above is the only path back.
- `UI/AGENTS.md` remains the nearest-owner doc for the rule; this ADR is the
  canonical record. No code change is required.
- Related follow-ups live in ADR-0123 (compile-strictness parity of the
  dual-compile) and ADR-0131 (CI contract wording).

## Alternatives
- Add `UI.Tests.csproj` to `Mesen.sln` now (implicit in ADR-0060's framing):
  rejected — the win-x64/AOT restore behaviour is unverifiable from the
  non-Windows actor, and a red Windows build would be the first signal.
- Add it with `Build.0` disabled for `Release|x64` (ADR-0054's revisit recipe):
  kept only as the documented fallback for the revisit, not done now, because
  nothing needs solution-wide discovery today.
- Leave the decision solely in `UI/AGENTS.md` (status before this ADR):
  rejected per ADR-0060/0066 — inconsistent with how the project records
  cross-cutting trade-offs.
- ADR-0065 (auditor-b meta: issues 1/2/4/9 were one refracted concern; the
  "recorded in T5 after T1" complaint was process critique of a correct
  outcome): no architectural content; retired by this consolidation. Likewise
  ADR-0073, ADR-0080 and ADR-0083 were process lore (definition-of-done for
  boundary moves, closeout hygiene of the since-deleted
  `docs/roadmap/plano-testes-unitarios.md`, follow-up queueing) and carry no
  architectural decision — they are retired without a successor beyond this
  note.
