# ADR-0123: UI/Logic host-free firewall: csproj strictness parity, csproj-derived scan, CI-wired

- Status: accepted (all five checklist items implemented 2026-08-29; reflected in the csproj, the AGENTS docs, the firewall script and the makefile/CI wiring)
- Date: 2026-08-27
- Consolidates: ADR-0055, ADR-0057, ADR-0061 (part a: firewall wiring), ADR-0062, ADR-0063, ADR-0067, ADR-0071, ADR-0073

## Context
`UI/Logic/*.cs` must stay host-free (BCL + `System.IO.Compression` only, no
`Avalonia`/`EmuApi`) so `UI.Tests/UI.Tests.csproj` can dual-compile it via
`<Compile Include="../UI/Logic/**/*.cs" />` with no `ProjectReference` to
`UI/UI.csproj`. Two guards exist: the dual-compile itself (a stray UI type
simply does not resolve, so `dotnet test` fails) and the grep script
`scripts/verify-ui-logic-firewall.sh` (checks the csproj for
`<RuntimeIdentifier>`/`<ProjectReference>`, then greps `UI/Logic/*.cs` for
`Avalonia|EmuApi` outside `//` comments).

Three gaps make the guarantee weaker than `UI/AGENTS.md` and
`UI.Tests/AGENTS.md` claim ("any accidental dependency breaks `dotnet test`
immediately"):

1. Property parity (ADR-0057/0062/0063). `UI.Tests/UI.Tests.csproj` sets
   `<ImplicitUsings>enable</ImplicitUsings>` and no `TreatWarningsAsErrors`;
   `UI/UI.csproj` has no `ImplicitUsings` (0 matches) and sets
   `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` (line 33, with
   `WarningsNotAsErrors` for IL2026/IL2070/IL2075/IL2104/IL3050/IL3053). The
   test compile is therefore the *looser* of the pair: a Logic file that omits
   `using System;` or emits a warning passes `dotnet test` and fails the real
   Windows `msbuild -t:UI`. ADR-0062 built `UI/Logic/**` under a scratch csproj
   with strict settings and found 0 warnings/0 errors, so nothing is broken
   today — the guarantee is nominal, not false in effect.
2. Scan set (ADR-0067/0071). The script hardcodes `logicDir="UI/Logic"`, but
   the csproj also dual-compiles `../UI/Interop/InteropEnums.cs` (Phase 2:
   `ConsoleType`/`CheatType` split out of the Avalonia-tainted `EmuApi.cs`).
   That file sits in a folder where `DllImport`/Avalonia usage is the norm and
   is not scanned (it currently contains 0 `DllImport`). Blast radius is
   diagnostics only — a bad edit still breaks `dotnet test`, just with an
   opaque "namespace not found" instead of the firewall's explanatory error.
3. Wiring (ADR-0061a). `verify-ui-logic-firewall.sh` is referenced only from
   `UI/AGENTS.md:92` (Verification) and `scripts/AGENTS.md:107`; it is not in
   the `makefile` (the `unit-tests` target runs `dotnet test` alone) nor in any
   `.github/workflows/*`. A convention no command runs decays at the first
   contributor who does not read `AGENTS.md`.

ADR-0055 wanted the compile named "the authoritative gate" and the grep a
pre-check; ADR-0063 correctly sequenced this after parity, because a compile
configured strictly weaker cannot bear that authority.

## Decision
Make the firewall's guarantee real, in this order:

- [x] `UI.Tests/UI.Tests.csproj`: remove `<ImplicitUsings>enable</ImplicitUsings>`
      (matching `UI/UI.csproj`, which does not set it) and add
      `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>`. Fix any test-side
      `using` fallout in `UI.Tests/**` that the removal exposes.
- [x] `UI.Tests/AGENTS.md` Local Contracts: add the rule "properties affecting
      compilation of `../UI/Logic` and `../UI/Interop/InteropEnums.cs` must stay
      at parity with (or stricter than) `UI/UI.csproj`".
- [x] `UI/AGENTS.md`: name `UI/Logic/` as the host-free boundary with the
      allowed-dependency list (BCL + `System.IO.Compression`), and state that
      after parity the dual-compile is the contract and the grep script a fast
      pre-check with readable diagnostics.
- [x] `scripts/verify-ui-logic-firewall.sh`: derive the scanned file set from
      the csproj's `<Compile Include="../...">` entries (globs expanded,
      relative to `UI.Tests/`) instead of the hardcoded `UI/Logic`, so
      `InteropEnums.cs` and any future dual-compiled path are scanned.
- [x] Wire the script into the automated path: add it to the `unit-tests`
      makefile target (or a `verify` target that `unit-tests` depends on) and
      as a step in the `ui-tests` job of `.github/workflows/unit-tests.yml`
      before `dotnet test`. Update the Verification blocks in `UI/AGENTS.md`,
      `scripts/AGENTS.md` and `.github/AGENTS.md` accordingly.

## Consequences
- Once parity lands, `dotnet test` green implies the `UI/Logic` half of the
  Windows UI build is green for compile-level concerns; the ubuntu job stops
  giving false confidence.
- `TreatWarningsAsErrors=true` in the test project also applies to test code
  under `UI.Tests/**`; warnings there become failures (acceptable — the suite
  is small).
- The firewall script becomes self-updating with respect to what the csproj
  dual-compiles; adding a `<Compile Include>` automatically widens the scan.
- CI cost: one extra shell step (sub-second).
- Process note (from ADR-0073, kept as a consequence rather than a rule):
  when a later phase moves code across the host-free boundary, updating the
  csproj, the firewall scan, and the contract docs is part of that change's
  definition of done, not a follow-up.

## Alternatives
- Enable `ImplicitUsings` in `UI/UI.csproj` instead of dropping it in the test
  project (ADR-0057's second branch): rejected — touches the shipped app's
  build for a test-only concern.
- Move host-free shared types into a dedicated folder the script already
  covers (ADR-0067's second branch): rejected — `InteropEnums.cs` is deliberately
  kept in `UI/Interop/` next to `EmuApi.cs`; deriving the scan from the csproj
  is cheaper and does not fight the code layout.
- Treat the scan gap as "not worth an ADR" (ADR-0071, which also wrongly
  asserted the repo keeps no ADR directory): the diagnostics assessment is
  right, but the boundary definition is an architectural fact worth one record.
- Name the compile "authoritative" without fixing parity first (ADR-0055 as
  written): rejected per ADR-0063 — the compile is currently the weaker check.
- Leave the script documentation-only (status quo): rejected per ADR-0061 —
  unenforced conventions decay.
