# ADR-0158: No `NES_ONLY` / `LessUI` build modes — the console reduction already took the win

- Status: proposed
- Date: 2026-09-05
- Related: ADR-0157 §3 (runtime mode, not compile-time), ADR-0007 (Core source-manifest guard), ADR-0131 (`unit-tests.yml` contract), ADR-0155 (header dependency tracking), PRD Part A slice H8, `docs/roadmap/AGENTS.md` (product consoles), `makefile`, `.github/workflows/build.yml`, `.github/workflows/unit-tests.yml`

## Context

PRD slice H8 proposed importing `ky12138/MesenCE`'s `NES_ONLY` (`adc1a6a2`)
and `LessUI` (`42e0ee27`) build modes, for "a smaller and faster headless/CI
build". The slice was recorded from a fork survey, not from a measurement,
and it carried its own caveat: "no ADR yet — needs one if it changes what CI
builds". This ADR is that decision, and it is a decision **against**.

### What the prior art actually is

Both commits are **C# only**. Neither touches a single file under `Core/`,
`InteropDLL/` or the `makefile`; the native `MesenCore` library they produce
is byte-for-byte the same one an unmodified build produces. `NES_ONLY` and
`LessUI` are MSBuild properties in `UI/UI.csproj` that add
`<Compile Remove>` / `<AvaloniaXaml Remove>` item groups plus a
`DefineConstants` symbol, backed by `UI/NesOnlyStubs.cs` (162 lines of stub
types re-declaring what the exclusions took away) and `#if` fences threaded
through 22 further UI files — `Configuration.cs`, `ShortcutHandler.cs`,
`MainMenuViewModel.cs`, `ConfigViewModel.cs`, `ResourceHelper.cs`,
`DbgImporter.cs` and so on.

So the slice's own premise — "compile-time exclusion of the non-NES cores" —
does not describe the source. The cores are not excluded by it at all.

### What is left to exclude here

`main` has already been through the console reduction (the retired
`plano-reducao-consoles`). `Core/` today contains `NES`, `Gameboy`, `GBA`,
`SMS`, `Shared`, `Debugger` and `Netplay` — there is no SNES, PC Engine,
WonderSwan or ColecoVision core to remove, only the SNES *gamepad* port
devices `docs/roadmap/AGENTS.md` deliberately keeps as input for the
remaining cores.

Resolving the fork's exclusion lists against this tree, file by file:

| Mode | Paths it excludes | Already absent here | Still present | Of those, removable |
|---|---|---|---|---|
| `NES_ONLY` | 130 | 80 | 50 | **0** |
| `LessUI` | 13 | 0 | 13 | **4** |

Of `NES_ONLY`'s 50 survivors, 46 are Game Boy / GBA / SMS UI — three of the
four product consoles — and 4 are the SNES gamepad views AGENTS.md keeps.
`LessUI`'s 13 are the HD Pack builder (2), the video/movie recorder (7) and
Netplay (4); the first nine are the MesenCE product itself (Phase 5, Phase 9,
`HdPackBuilderViewModel.ExtractAudio()`), which leaves four Netplay window
files — 0.6% of the 619 `.cs`/`.axaml` files under `UI/`.

The addressable surface of slice H8, after respecting product scope, is four
UI files and nothing in C++. Upstream did the shrinking already, by deleting
code rather than by fencing it.

### Where the time actually goes

Measured on this tree, macOS/arm64, clang, `-j8` on 8 cores (Darwin sets
`LTO := false`, so the link is cheap here; Linux CI links with LTO):

| Step | Time |
|---|---|
| Clean `make -j8 core` (full native lib, 206 Core + Utilities/SDL/Lua/7z TUs) | **149.5 s** wall, 416 s CPU |
| — of which: the 61 `Core/Gameboy` + `Core/GBA` + `Core/SMS` objects | **~38 s** (26%) |
| — of which: the link step alone | 1.3 s |
| No-op incremental `make -j8 core` (ADR-0155 header deps) | 0.8 s |
| `make core-unit-tests`, cold | **39.3 s** |
| `make doc-checks` | **51.7 s** |
| `dotnet publish UI` cold / warm | 38.8 s / 25.5 s |

The 26% attributable to non-NES cores is the largest number in the table, and
it is entirely product code: GB/GBC, SMS/GG and GBA are shipped consoles, and
F2 (HD Pack GB/SMS) depends on them. There is no measured saving available
from excluding non-product code, because there is no non-product code left.

### Which CI job would use the mode

None.

- `unit-tests.yml` (ADR-0131) never builds `MesenCore`: its native cost is
  `make core-unit-tests`, a self-contained compile of 23 explicitly listed
  `Core/`/`Utilities/` sources. A mode that excludes cores cannot make it
  faster, because it never compiled them.
- `build.yml`'s 14 jobs (6 Linux, 2 AppImage, 4 macOS, 2 Windows) produce the
  **shipped artifacts**. A release build must contain every product console
  and the HD Pack builder and recorder, so it cannot run in either mode.
- `tests.yml` runs the Windows ROM regression suite against a full build.
- The headless tools (`capture-tool`, `spike-sound-driver`, `roles-probe`) all
  depend on the `core` target and are not built by any workflow.

`build.yml` already installs and configures `ccache` on every Linux and macOS
job and already builds with `make -j$(nproc) -O`. The cheap parallelism and
the cheap caching are in place.

## Decision

**Do not add `NES_ONLY`, `LessUI`, or any other compile-time build mode that
excludes cores or product UI.** Slice H8 is closed as "measured, not worth
it". No symbol is introduced, no `#ifdef` or `#if` is added, `UI/UI.csproj`
gains no `Remove` item group, and CI builds exactly what it builds today.

Four reasons, in order of weight:

**1. There is nothing left to exclude.** Zero of `NES_ONLY`'s 130 exclusions
and four of `LessUI`'s 13 are removable here without dropping product. A
permanent build mode whose whole reach is four Netplay window files is not a
trade worth a second compilation configuration.

**2. It would fragment the build for no measured gain.** This is ADR-0157 §3
in a new costume. That section rejected `#ifdef LIBRETRO` in `Core/` because
"the headless harness and the shipped GUI no longer exercise the same code",
and the cost is permanent. Moving the fences from C++ to C# does not change
the argument: the fork needed 22 fenced files plus a 162-line stub file to
keep a `NES_ONLY` build compiling, and every one of those fences is a place
where the mode CI runs and the mode users run can drift apart. There is one
binary, and what varies varies at runtime.

**3. ADR-0007's guard would become quietly ambiguous.**
`scripts/check-core-manifest.sh` diffs `find Core -name '*.cpp'` **on disk**
against `Core.vcxproj`'s `<ClCompile>` entries. It has no view of which of
those files a given makefile invocation actually compiles. A C++ `NES_ONLY`
would therefore still pass the check while MSVC — which has no equivalent
mode — kept compiling the excluded sources, so the two manifests would agree
textually and mean different things. The guard would stop guarding the thing
it exists to guard. Keeping the makefile's glob total is what keeps the check
honest.

**4. The remaining CI time is not compile time.** `make doc-checks` (51.7 s)
now costs more than the whole native step of the cheap job, and the UI
publish costs about as much as the core-unit-tests compile. A build mode
attacks the one column that is already the smallest.

### What to do instead, if the build is ever the bottleneck

Recorded here so H8 is not re-proposed from the same premise:

- **`make core-unit-tests` is one serial `clang++` invocation.** All 23 TUs
  compile in a single command with no `-j`, taking 39.3 s single-threaded on
  a machine with 8 idle cores. Splitting it into per-object rules would let
  `make -j` take it to roughly 6–10 s — the only real, measured CI saving in
  this neighbourhood, worth about four times what the fork's modes could
  offer, at no cost in source fences. It compiles the same sources into the
  same binary, so it needs no build mode and no ADR of its own; it is left
  out of this change only because `makefile` and `scripts/core_unit_tests.cpp`
  are under concurrent edit.
- **`ccache` locally.** CI has it; a developer machine without it pays the
  full 149.5 s on any clean build. That is a bigger single-developer win than
  the 38 s the non-NES cores cost, and it costs one `brew install`.
- **Trim what a job builds, not what a build contains.** Splitting targets so
  a job builds only what it tests is the same win with none of the fences —
  and `unit-tests.yml` is already the proof, since it deliberately builds no
  core at all.
- **Runtime selection.** If a future headless job genuinely wants a narrower
  emulator, it selects it at runtime (ADR-0157 §3), the way the headless path
  already does.

## Consequences

H8 ships no code. The measurement is the deliverable, and it retires a slice
rather than adding a maintenance surface: no second compilation
configuration, no stub file shadowing real types, no `#if` fence that lets CI
and the shipped build diverge, and `check-core-manifest.sh` keeps meaning
exactly what ADR-0007 says it means.

The cost is that the 26% of the native build spent on the Game Boy, GBA and
SMS cores stays spent, on every clean build, forever. That is the correct
price: they are product. Anyone revisiting this should re-run the table above
first — the decision is a function of those numbers, and it would change if a
console were ever dropped from the product again.

The `core-unit-tests` parallelisation above is left on the table as a
follow-up, and it is where the next person looking for build time should go.

## Alternatives

**Import `NES_ONLY` as-is.** Rejected: it excludes Game Boy, GBA and SMS UI,
three of the four product consoles (`docs/roadmap/AGENTS.md`), and 80 of its
130 exclusions name files this tree deleted years of slices ago. It would
have to be rewritten before it could even be applied, and what survived the
rewrite is the four SNES gamepad views AGENTS.md explicitly keeps.

**Import `LessUI` as-is.** Rejected more sharply: it excludes
`HdPackBuilderWindow`, `HdPackBuilderViewModel`, `VideoRecordWindow` and
`MovieRecordWindow`. In upstream Mesen those are optional extras; in MesenCE
the HD Pack builder and the recorder are the product (Phase 5, Phase 9). The
mode is a fork's answer to a fork's problem.

**A narrowed `LessUI` covering only Netplay.** Rejected: four files out of
619 (0.6%), and Netplay's UI is not what makes a build slow — the four files
do not measurably move `dotnet publish`. It would buy a permanent second
configuration for noise.

**A C++-side `NES_ONLY` we design ourselves** (excluding `Core/Gameboy`,
`Core/GBA`, `Core/SMS` from `CORESRC` for a headless-only target). Rejected
on all three counts: the 38 s it saves is product code, no CI job would build
in that mode, and it puts `check-core-manifest.sh` in the ambiguous position
described under Decision 3. It is also strictly more invasive than the prior
art it claims to import — the fork never touched C++ at all.

**Do nothing and leave H8 open.** Rejected: an open slice invites a later run
to implement it from the same wrong premise. The premise ("exclude the
non-NES cores") is factually false about this tree, and the record should say
so with numbers.
