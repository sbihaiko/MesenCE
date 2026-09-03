# ADR-0120: Last-priority subfolder fallback for MEP zip discovery

- Status: accepted
- Date: 2026-08-26
- Extends ADR-0040 (storage/discovery precedence) and ADR-0049 (sibling
  folder convention, zip-named-as-ROM), without reordering either.

## Context
MEP-v1 §2.1 accepts a zip pack in `EnhancementPacks/` in exactly two shapes:
a `pack.json` at the zip root (ADR-0040 rule 1), or a zip whose base file
name equals the ROM's name — "zip = the folder, zipped" (ADR-0049 rule 1).
`MepPackManager::PrepareZip` enforces this today with no recursion: it
builds a normalised `(entry, path)` plan from the zip's entry list, sets
`hasPackJson` only when an entry normalises to exactly `"pack.json"`
(Core/Shared/EnhancementPacks/MepPackManager.cpp:399-411), and rejects the
whole pack when that is false and the zip's base name does not
case-insensitively equal `_romName` (MepPackManager.cpp:412-415) — no entry
is ever inspected for a *subfolder* named after the ROM. Independently,
`MepPack::DetectConventionLayout()` only ever probes
`RootFolder/kConventionProbe[i]` and `RootFolder/auto/kConventionProbe[i]`
(Core/Shared/EnhancementPacks/MepPack.cpp:53-80) — again, the root passed in,
never a descendant. Both facts were confirmed directly by reading the
current source during this decision, not inferred.

Real community packs do not always ship this way. A release zip built by
`git archive`/GitHub Releases commonly wraps its payload in one extra
directory (`<Repo>-<tag>/`, a promo/screenshots sibling, or both) — see the
provenance note below for the specific pack that motivated this ADR. Under
today's rule such a zip has no root `pack.json` and its base name (the
download's file name) does not equal the ROM name, so it is rejected outright
even though a valid MEP-shaped layout exists one level down.

## Decision

### 1. Additive, lowest-priority extension — not a precedence change
This ADR adds a **fourth, last-resort** rule after the three ADR-0040/
ADR-0049 rules (sibling folder → `HdPacks/<Game>/` legacy →
`EnhancementPacks/` containers matched by pack.json-root or
zip-name-equals-ROM). It fires **only** when a zip candidate has already
failed both existing zip-acceptance tests (no root `pack.json`, base name ≠
ROM name). It never changes which candidate wins when an existing rule
already matches, never widens what counts as a sibling folder or a
`pack.json`-rooted container, and never applies to directory packs (which
have no "wrapper" ambiguity — a directory's identity is its own path). The
existing precedence chain, and the "first pack per section wins" tie-break
of ADR-0040 rule 4, are unchanged.

### 2. A pure, I/O-free function that `PrepareZip` consults
The subfolder search is implemented as a pure function — no `ZipReader`
call, no filesystem access, no cache/extraction side effect — that takes the
already-built, already-normalised entry-path list `PrepareZip` computes
before its accept/reject decision (the `plan` vector at
MepPackManager.cpp:399-411) plus the ROM name, and returns an optional
discovered prefix. `PrepareZip` calls it exactly once, only on the path
where `hasPackJson` is false and the name check has already failed, replacing
what is today an unconditional `return false` with: call the fallback: if it
finds no unambiguous prefix, reject exactly as before (same `error` string,
same `return false`); if it finds one, proceed with the normal extraction
loop and combine the extraction root with the discovered prefix through
`MepPack::NormalizeRelativePath` to produce `outFolder`.

**`PrepareZip`'s public contract is held fixed on purpose.** Its declared
signature stays exactly `bool PrepareZip(const string& zipPath, const
string& cacheRoot, string& outFolder, string& error)` — no new parameter,
no new output, no change to what `outFolder`/`error` mean to callers. The
fallback is entirely an internal decision about *which prefix under the
already-planned extraction* becomes the pack root; every caller downstream
of `PrepareZip` keeps working against a directory that looks exactly like a
convention-shaped pack, because that is what `outFolder` still points at.
This is also why the function is placed to be reachable without dragging
`ZipReader`/miniz into `core-unit-tests`: it operates purely on
`vector<string>` entry paths already in memory, so it is unit-testable with
literal fixtures with no zip I/O at all, independent of where in the
`MepPackManager`/`MepPack` translation units it is declared and defined.

Depth and entry-cap bounds (max depth 4 path segments, max 2000 visited
entries, fail-closed on overflow — i.e. treat an overflow as "no candidate
found", never as a crash or an unbounded scan) apply identically to this
function and to its C#/Python mirrors (§3). "Depth" is defined as the count
of `/`-separated segments in the normalised entry path (e.g.
`Contra80s-v1.1/Contra (U) [!]/hires.txt` is depth 3); this definition is
pinned in the function's own comment in each language, since the task
description does not supply a formula and a silent divergence here would
make the three implementations agree on their own tests while disagreeing
with each other.

Ambiguity is fail-closed: if more than one candidate subfolder in the entry
list independently satisfies the acceptance test, the function reports "not
found" rather than guessing, and `PrepareZip` falls through to the existing
rejection — same philosophy C# and Python apply (§3), even though the test
each one runs is different.

### 3. C++ matches by name; C#/Python match by structure — an intentional asymmetry
`PrepareZip` has something the two validators do not: `_romName`, the exact
ROM identity of the file being loaded. So the C++ fallback's acceptance test
is a **name match** — a single-segment subfolder whose name equals the ROM
name (case-insensitive), mirroring the zip-name-equals-ROM rule it extends.

`MepZipValidator.Validate(ZipArchive)` (C#) and `mep_lint.py` (Python) run
at points where no ROM name is available — `Validate` is called from
`InstallPack` in `UI/ViewModels/EnhancementPacksViewModel.cs:121`, which
opens a generic file-picker dialog and copies the selected zip into the
shared `PacksFolder` (`UI/ViewModels/EnhancementPacksViewModel.cs:110-133`)
with no ROM in scope at that point, and `mep_lint.py`'s CLI takes only a
downloaded pack path (`argv[1]`) for the community-pack CI workflow
(`.github/workflows/community-pack-validate.yml`), not a target ROM. Their
fallback is therefore **structural**: does a candidate subfolder, treated as
if it were the zip root, satisfy the existing `LayerProbes` /
`PROBES`/`AUDIO_ALT_PROBE` convention-probe test (`textures/hires.txt`,
`audio/hires.txt` or `audio/fingerprints.json`, `synth/preset.cfg`)? This is
deliberately looser than the C++ name match — it will accept a subfolder
regardless of what it is named, as long as its contents look like a pack —
and it is deliberately **not** loosened further into "accept the first
plausible candidate": more than one structurally-valid candidate subfolder
is ambiguous and is rejected, for the same fail-closed reason as §2.

This is accepted as an intentional, documented asymmetry rather than
something to unify immediately, because unifying it requires giving the
validators the one piece of context they currently lack: the ROM name.
**Named follow-up (not this task):** add an optional ROM-name parameter to
`MepZipValidator.Validate` and to `mep_lint.py`'s CLI (e.g. an optional
second argument) so that, when a caller has that context, the validators
can tighten to the same name match C++ uses instead of only the looser
structural one. *Status update (ADR-0121, 2026-08-27):* the Python half is
implemented — `scripts/mep_lint.py` accepts an optional second positional
ROM name and, when the structural fallback finds nothing, tries the
ROM-name-anchored `find_fallback_subfolder_by_name`; the CI workflow can
supply the name from the issue form. The C# validator
(`UI/Logic/MepZipValidator.cs`) remains structural-only
(`FindStructuralFallbackPrefix`, no ROM-name parameter). At the time of this
ADR **neither existing caller had that context**:
`InstallPack` copies into the shared `PacksFolder` with no ROM selected
(§3 above), and CI validates a downloaded pack with no ROM at all — both
would keep using the structural path even after the parameter exists.
Taking the tightened check therefore also requires a *new* caller — a
per-ROM install path/UI action that knows which ROM it is installing for
and passes that name through `Validate` — not just adding a parameter to
the existing installer flow, which does not have a ROM to give it. Until
that new caller exists, a validator-side accept is a *necessary* condition
(the layout looks pack-shaped) but not the *sufficient* one C++ enforces at
load time (the layout is also for this ROM) — this gap is intentional, not
an oversight, and is why the validators are pre-flight checks, not the
authority `PrepareZip` is for what actually loads.

Deferral (2026-09-01): the C# half of the §3 follow-up (optional ROM-name
parameter on `MepZipValidator.Validate`) stays deferred. Re-verified on this
date: `MepZipValidator.Validate(ZipArchive)` still has exactly one
production caller, `InstallPack` in
`UI/ViewModels/EnhancementPacksViewModel.cs:188`, which still opens a
generic zip file-picker and copies into the shared `PacksFolder` with no ROM
in scope, so a new parameter would have no caller that can supply a value —
dead code that only the unit tests would exercise. The Python mirror also
does more than the C++ exact match: `find_fallback_subfolder_by_name`
(`scripts/mep_lint.py:323`) falls back to a region/flag-tag-normalised
comparison via `normalize_rom_core_name`, so a faithful C# port is not a
contained change, and an exact-only C# variant would introduce a third,
divergent semantics for the same parameter. Trigger to pick it up: the
per-ROM install caller named above (a UI action or the community auto-install
path that knows which ROM it installs for) — implement the parameter in the
same change as that caller, porting the normalised comparison from
`mep_lint.py` and covering it in `UI.Tests/Mep/MepZipValidatorTests.cs`.

### 4. Deferred: a standalone C++ E2E zip-pipeline test harness
This task deliberately does **not** build a driver/executable that links
`MepPackManager.cpp` + `ZipReader.cpp` + miniz + `ArchiveReader` to exercise
`PrepareZip` end-to-end against a real `.zip` file (extraction, cache-stamp
reuse, disk I/O included). §2's pure-function extraction is what makes the
new fallback *logic* testable today without that harness — `core_unit_tests`
(the existing link-safe, no-`ZipReader` seam at
`scripts/core_unit_tests.cpp` / `Makefile`'s `core-unit-tests` target) can
exercise the fallback function directly with literal `std::vector<string>`
fixtures. What it cannot exercise is the surrounding I/O: real zip
extraction, the `.mep-source` stamp cache-reuse branch, `NormalizeRelativePath`
combined with a real `FolderUtilities::CombinePath` on disk, or zip-slip
rejection against actual archive bytes. A standalone E2E harness for that
full pipeline is named here as a **separate, not-this-task follow-up** —
scope was deliberately kept to the pure decision function plus its
call-site wiring, matching the Scope Boundaries of the originating task.

Deferral (2026-09-01): still deferred. What exists today, re-verified on
this date: `scripts/core_unit_tests.cpp` exercises only the pure
`MepPack::FindFallbackSubfolder` with literal fixtures (no zip bytes);
`scripts/headless_record.cpp` is the C++ headless driver for audio/HD-pack
recording and MEP log capture, and it loads packs from folders placed in
the scratch home; `scripts/verify_community_install_from_zero.py` covers the
community *install* pipeline end-to-end (No-Intro sha1 → catalog match →
allow-listed download → sha256 check → extraction → headless load), but its
extraction is done in Python (`extract_legacy_pack`, mirroring the C#
`LegacyHdPackInstall`) into `HdPacks/<romName>/` as a folder, so the C++
`PrepareZip` zip path (real extraction, the `.mep-source` stamp cache-reuse
branch at `MepPackManager.cpp:634`, zip-slip rejection on real archive
bytes, the §2 subfolder fallback on a real wrapped zip) is not what it
proves; `scripts/mep_live_validate.py` likewise extracts to an
`EnhancementPacks/<rom>/` folder first. Only `scripts/gen_mep_test_pack.py`'s
`zip`/`slip` kinds put a real zip through `PrepareZip`, and that is a manual
`headless_record ... log` inspection, not an asserting harness. Trigger to
pick it up: a regression or bug report in `PrepareZip`'s zip path (cache
reuse, zip-slip, or the wrapped-subfolder fallback) that the pure-function
tests cannot reproduce, or the real `Contra80s.zip` inspection named under
Provenance being scheduled — either would justify a `Makefile` target that
links `MepPackManager.cpp` + `ZipReader.cpp` + miniz and asserts on
`outFolder`/`error` for `gen_mep_test_pack.py`-generated fixtures.

## Provenance of the motivating claim (see also AC-8)
The pack that motivated this fallback is referenced by this repository's own
issue #3, "[Community Pack] Contra80s (NES)"
(https://github.com/sbihaiko/MesenCE/issues/3), which names the target as
`Contra (USA)` / NES and links the pack at
`https://github.com/TasticHacks/Contra80s/releases/download/1.1/Contra80s.zip`
(release `1.1`, asset `Contra80s.zip`, reported size ≈91MB) — matching the
README's existing TasticHacks/Contra80s screenshots and credit line.

**What was independently verified by reading the current source in this
decision session:** that `MepPackManager::PrepareZip`
(MepPackManager.cpp:399-415) and `MepPack::DetectConventionLayout()`
(MepPack.cpp:53-80) require an exact root layout today — `pack.json` (or a
convention probe) must sit directly at the path `PrepareZip` extracts to,
with **no recursion** into any subfolder for either check. This is a fact
about the current code, confirmed by direct reading, independent of any
claim about the real Contra80s zip.

**What was *not* independently re-verified:** the real, published
`Contra80s.zip`'s actual byte-for-byte internal structure. Neither this
decision session nor (per the originating task's own stated assumption) the
implementing session downloaded and inspected the ~91MB release asset; the
"wraps its payload one level down" shape used for the Contra80s-style test
fixtures (e.g. `Contra80s-v1.1/Contra (U) [!]/hires.txt`) is the shape
described in the task/issue text and in this project's own memory of
GitHub-Releases-style zips in general, not a structure confirmed by opening
the actual archive.

Consequently, any statement that "the real Contra80s pack would not load
today without this fallback" is a claim **qualified by that coverage gap** —
it follows deductively from the independently-verified fact that
`PrepareZip`/`DetectConventionLayout` require an exact, non-recursive root
match, applied to the *described* (not independently re-inspected) shape of
the actual release zip. It is not itself an independently confirmed
end-to-end observation of the real file. A future pass that downloads and
runs the real `Contra80s.zip` through `PrepareZip` (or `mep_lint.py`) would
close this gap and could be folded into the E2E harness named in §4.

## Consequences
- A zip that today gets `error = "zip has no pack.json at its root"` for
  wrapping its content one level down in an unambiguous, ROM-named (C++) or
  pack-shaped (C#/Python) subfolder now loads/validates instead of being
  rejected — with zero change to how any already-accepted pack is discovered
  or which pack wins a given section.
- The fallback adds one more code path to reason about in each of three
  languages, each bounded by the same depth/entry-cap constants
  (`verify_mep_fallback_constant_parity.sh` keeps them in lockstep) and the
  same fail-closed-on-ambiguity philosophy, even though the acceptance test
  itself differs by design (§3).
- `PrepareZip` callers, `outFolder`/`error` semantics, and every other
  caller of `MepPack::DetectConventionLayout()` are unaffected — the
  fallback is invisible to them because it only decides *what* gets
  extracted where, not *how* it is consumed afterward.
- Two follow-ups are explicitly deferred, not silently dropped: an optional
  ROM-name parameter for `MepZipValidator.Validate`/`mep_lint.py` (§3 — since
  done for `mep_lint.py`, still open for the C# validator; see ADR-0121), and a
  standalone C++ E2E zip-pipeline harness (§4).

## Alternatives
- **Recurse in `DetectConventionLayout()` itself** (search subfolders at
  load time, not discovery time): rejected — conflates "which folder is the
  pack root" (a discovery-time, zip-specific question, since directory packs
  have no wrapper ambiguity) with "does this root have a convention layout"
  (unchanged, AC-3), and would have required extending
  `DetectConventionLayout()`'s signature.
- **Give C# and Python the ROM name now** so all three match by name:
  rejected for this task — both call sites (installer UI, CI's black-box
  `mep_lint.py` invocation) would need call-site changes, explicitly out of
  the originating task's scope; recorded instead as the §3 follow-up.
- **Unbounded/recursive subfolder search:** rejected — unbounded traversal
  over an attacker-influenced entry list (a zip can claim any entry names)
  is a resource-exhaustion surface; the depth-4/entry-cap-2000 bounds, shared
  across all three languages, close it deterministically.
- **Accept the first plausible candidate instead of rejecting on
  ambiguity:** rejected — silently picking one of several equally-plausible
  subfolders would make pack loading non-deterministic across a re-inspected
  zip whose entry order changes, and would contradict the fail-closed
  posture ADR-0040's zip-slip validation already establishes for this exact
  code path.
