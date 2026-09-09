# ADR-0007: Guard against Core source-manifest drift between the makefile glob and Core.vcxproj

- Status: accepted
- Date: 2026-08-24
- Updated: 2026-09-09 — the guard covers `Utilities/` as well as `Core/`. The
  gap was not theoretical: `Utilities/LiveRecordFormat.cpp` (the live-recorder
  wire format, ADR-0169) shipped unlisted in `Utilities.vcxproj` and broke the
  Windows CI jobs for four consecutive pushes with `LNK2001` on
  `LiveRecordFormat::ComposePpm`/`ComposeStatusJson`/`AtomicWrite` — symbols
  nobody had touched, reported against `InteropDLL`'s link step, which is a
  long way from the missing project entry. `check-core-manifest.sh` now loops
  over both directories (Core, then Utilities) and exits non-zero if either
  drifts, so the same silent-rot class is caught for both manifests the
  makefile globs for C++. `SevenZip/` and `Lua/` stay out of scope: they are
  vendored C, not sources this project adds to.
- Related: ADR-0155 (header dependency tracking in the same makefile), ADR-0137 (`make doc-checks` runs `check-core-manifest.sh`)

## Context
Raised during decompose: The project maintains two independent source manifests — a globbing makefile and a hand-enumerated Core.vcxproj (308 explicit entries). Any work that adds Core sources builds green on macOS/Linux while the MSVC project silently drifts, and the current effort adds six new Core sources across three parallel tasks.

## Decision
Add a check script that diffs `find Core -name '*.cpp'` against Core.vcxproj's ClCompile entries and fails on drift. This is what shipped: `scripts/check-core-manifest.sh`, wired as the `check-manifest` target in the `makefile` (the `ui` target depends on it), so every build of the UI runs the check.

## Consequences
Windows builds stop rotting silently as squad tasks add Core sources; the check also protects every future task, not just this run. Core.vcxproj remains hand-enumerated, so adding a Core source still requires touching it — the script turns a silent drift into a build failure rather than removing the duplication.

## Alternatives
Convert Core.vcxproj to wildcard includes so the two manifests cannot diverge: not pursued — it changes the MSVC project shape upstream Mesen maintains explicitly, and the check script achieves the same protection without touching it. Rely on task briefs reminding actors to touch Core.vcxproj: has already proven unreliable (the manifests have drifted before) and does not survive parallel tasks.
