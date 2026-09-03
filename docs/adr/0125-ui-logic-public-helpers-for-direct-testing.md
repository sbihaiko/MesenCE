# ADR-0125: UI/Logic types may expose public helpers for direct unit testing

- Status: accepted (Option A picked by the user on 2026-08-28; checklist below is the work)
- Date: 2026-08-27
- Consolidates: ADR-0059, ADR-0066 (public-surface half; the sln half is ADR-0122)

## Context
`UI/Logic/MepZipValidator.cs` exposes `public static string? Validate(ZipArchive zip)`
(line 57) as its production entry point and also `public static bool
IsSafePath(string entryFullName)` (line 167). `Validate` is the only production
caller of `IsSafePath` (line 64); `IsSafePath` is public primarily so
`UI.Tests/Mep/MepZipValidatorTests.cs` can drive the shared fixture
`docs/specs/golden/mep/path-cases.txt` case by case without building a
`ZipArchive` per row, and so later code may reuse it.

This widens the extracted module's public contract for test visibility.
`UI/AGENTS.md` Work Guidance says where host-free helpers go (`UI/Logic/`,
paired tests under `UI.Tests/<Area>/`) and what they may reference, but is
silent on whether `UI/Logic/` types may widen their public surface purely for
direct unit testing or whether tests must go through the single production entry
point. With two extracted types this is trivial; as more helpers are extracted
(`MepPackListParser`, `DisabledPackList`, `CheatTypeDetector` already exist) the
question will otherwise be decided case by case.

`UI.Tests.csproj` dual-compiles the sources (no `ProjectReference`), so
`InternalsVisibleTo` is not a mechanism available here: `internal` members of
`UI/Logic` are already visible to the tests because they are compiled *into*
the test assembly. That changes the trade-off compared with a conventional
test project.

## Decision
**Option A — allow public test-facing helpers, documented** (chosen by the
user on 2026-08-28; Option B is recorded under Alternatives).

- [x] Add to `UI/AGENTS.md` Work Guidance: "`UI/Logic/` types may expose pure
      helpers publicly when a test needs to drive them directly (e.g.
      `MepZipValidator.IsSafePath` over `path-cases.txt`). Keep the production
      entry point the documented one; a `//` header line on the helper must
      name it as test-facing / reusable so its public status reads as
      intentional."
- [x] Add the same one-line note above `IsSafePath` in `MepZipValidator.cs`.

Rationale: the dual-compile already erases the public/internal distinction
from the tests' point of view, so keeping helpers `internal` buys no
encapsulation for the tests and only restricts reuse by other UI code;
`IsSafePath` is a genuinely reusable pure predicate. The value of a rule here
is consistency, and the cheapest consistent rule is "public is fine if the
header says why".

## Consequences
- The rule lives in `UI/AGENTS.md` so future extractions follow one
  convention.
- Slightly wider public API in `UI/Logic`; each test-facing public helper
  carries a header note. No code behaviour change.
- `UI.Tests` continues to compile the sources directly; no
  `InternalsVisibleTo` is added to `UI/UI.csproj`.

## Alternatives
- Option B — single entry point, helpers stay `internal` (change `IsSafePath`
  to `internal static`; record in `UI/AGENTS.md` that `UI/Logic` exposes only
  the production entry point publicly): rejected 2026-08-28 — one visibility
  edit today and a deliberate re-publicising for every future UI-side reuse,
  for no encapsulation gain under the dual-compile.
- Leave `UI/AGENTS.md` silent and keep deciding per file (status quo):
  rejected by ADR-0059/0066 — cheap to settle now while the surface is small.
- Route every test through `Validate(ZipArchive)` and build in-memory zips per
  fixture row: rejected — turns a table-driven fixture into slow, noisy setup
  for a pure string predicate.
- Add `InternalsVisibleTo("UI.Tests")` to `UI/UI.csproj`: not applicable — the
  test project does not reference `UI.csproj`; it compiles the sources.
