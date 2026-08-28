# scripts/

## Purpose

Headless C++ harnesses, Python spec/pack validators, and shell checks that
exercise Core logic without the Avalonia UI. Two families live here:
tools that run the emulator headlessly against a ROM (link `MesenCore`,
need `make core` first), and framework-free binaries/scripts that validate
pure logic with no emulator, no ROM, and no GUI.

## Ownership

Owns everything under `scripts/`. Does not own the Core/Utilities source
these tools call into, or the goldens under `docs/specs/golden/` (owned by
`docs/`) that some of them read as fixtures.

## Local Contracts

- No test framework in C++: harnesses are `main()` + manual checks that
  print `PASS`/`FAIL` per case and return a non-zero exit code on any
  failure (see `core_unit_tests.cpp`, `roles_probe.cpp`).
- A binary that links `Core/**/*.cpp` directly (no `InteropDLL` shared lib,
  no `core` prerequisite) must compile those `.cpp` files standalone -
  verify their `#include` list has no further undeclared link dependency
  before adding a makefile target for it.
- Compiled binaries (`core_unit_tests`, `roles_probe`, `headless_record`,
  `spike_sound_driver`) are build output, not source - never `git add` them.
  `.gitignore` at the repo root lists all four by name, so none of them show
  as untracked after building.

## Work Guidance

- `core_unit_tests.cpp` - Phase 4 of the now-completed unit-test plan (see
  git history for `docs/roadmap/plano-testes-unitarios.md`): exercises
  `ChannelRoleClassifier` (role/SFX decisions) and
  `MepPack::NormalizeRelativePath` / `MepPack::Parse` (zip-slip fixture +
  pack.json golden) with no `MesenCore` link at all - the only harness here
  that doesn't need `make core` first.
- `roles_probe.cpp` / `headless_record.cpp` / `spike_sound_driver.cpp` run
  the emulator headless against a real ROM; they link `InteropDLL`'s shared
  lib and need `make core` first.
- `validate-specs.py`, `mep_lint.py`, `mep_recipe.py`, `mep_compare.py`, `mep_render_audio.py`,
  `gen_hdpack_test_roms.py`, `gen_mep_test_pack.py`, `gen_mep_fallback_test_pack.py`,
  `make_gb_test_rom.py`, `validate_hdpack_dump.py` - Python spec/golden/pack
  validators and test-ROM/test-pack generators; no emulator dependency.
  `mep_lint.py` mirrors the ADR-0120 structural (name-agnostic) last-priority
  subfolder fallback that `Core::MepPack::FindFallbackSubfolder` (C++, name
  match) and `MepZipValidator.FindStructuralFallbackPrefix` (C#, structural
  match) implement, via its own `find_fallback_subfolder`/
  `FALLBACK_MAX_DEPTH`/`FALLBACK_MAX_ENTRIES` (reusing `PROBES`/
  `AUDIO_ALT_PROBE`); it fires only when the root-level convention scan
  found no section, and emits an info line naming the discovered path/depth.
  Every candidate entry is run through `safe_rel` before it can become the
  discovered prefix — a zip-slip-shaped entry (a `..` segment) is skipped,
  never treated as a valid pack root, matching the traversal guards
  `MepZipValidator.IsSafePath` (C#) and `MepPack::NormalizeRelativePath`
  (C++) already apply on their own candidate-scan paths.
  Because `pack.json` is itself one of the fallback's accept markers
  (`FALLBACK_SUFFIXES`), a `pack.json` found under the discovered prefix is
  fully re-run through `lint_pack_json` (parameterized by `root_prefix`) —
  a manifest is never accepted on presence alone, the same MUST-field/
  semver/sha1/`safe_rel` checks the root-level manifest gets apply to a
  fallback-discovered one too.
  `gen_mep_fallback_test_pack.py` generates six synthetic zip fixtures
  (`accept`: one Contra80s-shaped release-zip wrapper; `reject`: two
  structurally-valid, ambiguous subfolders; `malformed`: the same wrapper
  shape as `accept` but with an invalid `pack.json` inside it, proving the
  discovered manifest gets linted rather than just detected; `empty-path`:
  same wrapper, a valid `pack.json` whose `sections.textures.path` is `""`
  plus a broken `hires.txt` at the discovered prefix's root, proving an
  empty section path doesn't leave the textures layer unlinted;
  `root-hires`: same wrapper with no `pack.json` at all - only
  `synth/preset.cfg` makes the subfolder a candidate - plus a broken
  `hires.txt` loose at the discovered prefix's root, proving the legacy
  root-`hires.txt` branch is mirrored under the fallback prefix; `traversal`:
  zip-slip-shaped entries (`../evil/textures/hires.txt`, `../evil/synth/
  preset.cfg`) with no root `pack.json` and no ROM-name match, proving
  `find_fallback_subfolder`'s `safe_rel` guard refuses a `..`-segment
  candidate instead of discovering it as the pack root) that exercise it,
  mirroring `gen_mep_test_pack.py`'s CLI/docstring style.
  `mep_recipe.py` (F6.1, ADR-0138) is the stdlib interpreter of
  `docs/specs/MEP-recipe-v1.md` (`validate` / `dry-run` / `apply`). It
  reuses `mep_lint` discovery (`Source`, `discover_sections`,
  `find_fallback_subfolder`, `find_fallback_subfolder_by_name`,
  `find_top_level_nested_zip`, `safe_rel`, `parse_line`) and never walks
  a zip with a parallel implementation. `test_mep_recipe.py` is the
  framework-free acceptance check (unknown op / escaping path rejected;
  dry-run of a synthetic split pack is `mep_lint`-clean).
- `docs/specs/golden/mep-nes/` (ADR-0136) - NES-shaped golden MEP pack
  fixture (`pack.json` + `textures/hires.txt` + `textures/tiles.png`):
  `SHAPE_A` is captured under two distinct 8-hex-char palettes and
  `SHAPE_B` under one, giving `palettes_per_shape == 1.5`. It is a sibling
  root next to the GB golden at `docs/specs/golden/mep/` - never nested
  under it, since the two goldens exercise different `<system>` values
  (`nes` vs `gb`) and neither supersedes the other. Linted by
  `validate-specs.py`'s `lint_golden_packs()` tripwire alongside the GB
  golden, and consumed as the shared NES fixture by
  `test_mep_compare_auto_palettes.py` below.
- `test_mep_compare_auto_palettes.py` - fixture-based check (self-compares
  the shared NES golden at `docs/specs/golden/mep-nes/textures` (ADR-0136)
  against itself via `mep_compare.main()`, no ROM/build dependency, no
  inline hand-rolled fixture of its own) that `mep_compare.py`'s
  `stats["auto"]` dict reports `palettes_per_shape` alongside
  `stats["artist"]`; the expected `1.5` value is checked against that
  golden's actual 3-key/2-shape layout (`SHAPE_A` x {`PAL_1`, `PAL_2`} +
  `SHAPE_B` x {`PAL_1`}), not assumed.
- `test_mep_compare_render_dispatch.py` (ADR-0136) - framework-free check
  that `mep_compare.py`'s `render_original` dispatches per `<system>`:
  decodes `nes`/`gb`/`gbc`/`sms` tile+palette fixtures shaped per
  `docs/specs/hires-gbsms-v1-draft.md` S3.2 without raising, and raises a
  `ValueError` naming the rejected system and the supported list
  (`nes, gb, gbc, sms`) before any per-tile decode work, both for an
  unsupported `<system>` (e.g. `gba`) and for a palette hex string of the
  wrong width for the declared system.
- `validate_palette_variants.py` (F5.4b) - builds `headless_record` via
  `make capture-tool` if missing, records `roms/Zelda.nes` with the `hdpack`
  flag, and checks that `HdPackBuilder::ProcessTile` captures more than one
  distinct palette for at least one tile shape while never letting any single
  shape exceed `HdPackBuilder::MaxPaletteVariantsPerTile` (the cap that bounds
  per-shape growth from near-blank/flat tiles - see that constant's comment
  in `Core/NES/HdPacks/HdPackBuilder.h`). Needs `make core`/a real ROM, unlike
  the fixture-only validators above.
- `checks/verify_community_pack_validate_workflow.py` — stdlib+PyYAML
  structural checker for `.github/workflows/community-pack-validate.yml`
  (AC-2, AC-6 validate-side of the community-pack triage task): parses the
  reusable workflow's `workflow_call` inputs, the exact Project/Status/
  option/Pack-Hash ids, the host allow-list, the 300MB cap, the always-write
  `sha256` step, the unmodified `mep_lint.py` call, the Claude Code Action
  tool restriction + data-not-instruction prompt clause, the secret-name
  comment, and — by literal `uses:`/string match against this workflow's
  own text only, never by opening `community-pack-catalog.yml` — that it
  dispatches that catalog workflow gated on an "Aceito*" Status, and
  (F6.0) that the Classify pack step has `timeout-minutes`. Sibling
  checkers for the other community-pack deliverables land in this same
  `checks/` subfolder as later tasks add them; none needs its own AGENTS.md
  (same one-script-one-contract pattern as the checks below).
- `check-core-manifest.sh`, `check-file-loc.sh`, `verify-fase0-1-dox.sh`,
  `verify-ui-logic-firewall.sh` - repo-hygiene shell checks. All four are
  now invoked by `make doc-checks` (ADR-0137, roadmap slice H1):
  `check-core-manifest.sh` via the target's `check-manifest` dependency
  (itself still a dependency of `ui`/`core` on its own), then
  `verify-fase0-1-dox.sh`, `verify-ui-logic-firewall.sh`, and
  `check-file-loc.sh` (against `Core/Shared/Audio/MidiExporter.cpp 200`)
  run directly by `doc-checks`, in order, failing on the first non-zero
  exit. CI runs `make doc-checks` as its own step on the Linux and macOS
  build jobs, before "Build Mesen". `check-f5-4b-doc.sh` was deleted on
  2026-08-27 together with the plan header it guarded.
- `checks/` - per-deliverable acceptance-criteria verifiers for dev-squad
  runs (one script per AC, invoked directly by its AC's Verification
  command). Same PASS/FAIL-and-exit-code convention as the top-level shell
  checks above; no shared test framework. `checks/verify_claude_md_section.sh`
  guards `CLAUDE.md` (AC-10): the pre-existing "Rastreamento de bugs (GitHub
  Project)" section must stay byte-for-byte untouched (checked as an exact
  file prefix) while a new "Triagem de Community HD/MEP Packs (GitHub
  Project)" section is appended after it. `verify_community_pack_issue_template.py`
  parses `.github/ISSUE_TEMPLATE/community-pack.yml` with PyYAML and asserts
  the required fields/checkbox/labels/doc-link. `verify_hd_pack_authoring_doc.sh`
  checks that `docs/hd-pack-authoring.md` exists, is non-trivial, and cites
  `docs/specs/MEP-v1.md` §5.1/§5.2/§5.3/§6. `verify_community_pack_labels_script.sh`
  (AC-2, ADR-0138 F6.2a) parses the `LABELS` array of
  `ensure_community_pack_labels.sh` literally (not one representative grep)
  and asserts both the exact 12-entry count and the full expected name set,
  including the `assets:external` content-index label. `verify_community_pack_submitted_workflow.py`,
  `verify_community_pack_drift_check_workflow.py`, and
  `verify_gh_project_provenance_drift.py` verify the community-pack GitHub
  Actions workflows and their GH Project field-provenance assumptions.
  The submitted-workflow checker also asserts F6.0's concurrency
  expression (`cancel-in-progress` parsed as
  `${{ github.event_name == 'issues' }}`, not a comment grep).
  `verify_mep_fallback_adr.sh` (AC-7 of the MEP zip-fallback task) checks
  `.dev-squad/adr/0120-*.md` documents the subfolder fallback as an additive
  last-priority extension of ADR-0040/ADR-0049's precedence, a pure I/O-free
  function `PrepareZip` consults with its `outFolder` contract held fixed,
  the C++ (name match) vs C#/Python (structural match) asymmetry with its
  named ROM-name-parameter follow-up, and the standalone C++ E2E
  zip-pipeline harness deferred as a separate follow-up.
  `verify_mep_fallback_adr_provenance.sh` (AC-8, same ADR) checks it cites
  the TasticHacks/Contra80s provenance (issue #3 / the release download
  URL) and explicitly separates what was independently verified by reading
  `PrepareZip`/`DetectConventionLayout` today (exact root layout, no
  recursion) from what was not independently re-verified (the real
  published zip's byte-for-byte structure), qualifying any "would not load
  today" claim by that gap.
  `verify_mep_fallback_lint_fixture.sh` (AC-5) generates all six
  `gen_mep_fallback_test_pack.py` fixtures plus one `gen_mep_test_pack.py`
  regression fixture and runs the real `mep_lint.py` CLI against all seven:
  the Contra80s-shaped wrapper is accepted with a fallback info line naming
  the discovered path/depth, the ambiguous two-subfolder pack is rejected
  with no such line, a pre-existing pack.json-root pack's classification
  (and the absence of any fallback line) is unchanged, the wrapper with a
  malformed `pack.json` inside the discovered prefix is rejected with a
  JSON-invalid error naming that nested `pack.json` (not silently accepted
  on the manifest's mere presence), the wrapper with an empty
  `sections.textures.path` plus a broken discovered-root `hires.txt` is
  rejected (the empty path doesn't leave the textures layer unlinted), the
  manifest-less wrapper with a broken discovered-root `hires.txt` is
  likewise rejected (the legacy root-`hires.txt` branch is mirrored under
  the fallback prefix, not skipped), and the zip-slip-shaped candidate is
  rejected with no fallback info line (a `..` segment must never be
  discovered as a pack root).
  `verify_mep_fallback_constant_parity.sh` (AC-6) extracts
  `kMepFallbackMaxDepth`/`kMepFallbackMaxEntries` (C++, `MepPack.h`),
  `FallbackMaxDepth`/`FallbackMaxEntries` (C#, `MepZipValidator.cs`), and
  `FALLBACK_MAX_DEPTH`/`FALLBACK_MAX_ENTRIES` (Python, `mep_lint.py`),
  failing loudly (naming the offending language) when a constant is missing
  or unparseable in any of the three, and separately asserts the literal
  values 4/2000 and three-way cross-language equality.

## Verification

- `make core-unit-tests` - builds and runs `core_unit_tests` (no `core`
  prerequisite); every case must print `PASS` and the binary must exit 0.
- `make roles-probe` / `make capture-tool` / `make spike-sound-driver` -
  each depends on `make core` first.
- `python3 scripts/validate-specs.py` - specs/goldens under `docs/specs/`.
- `python3 scripts/test_mep_recipe.py` - MEP Recipe v1 interpreter
  (unknown op / escaping path rejected; synthetic split-pack dry-run is
  `mep_lint`-clean); PASS/FAIL per check, exit 0 only if all pass.
- `python3 scripts/test_mep_compare_auto_palettes.py` - `mep_compare.py`'s
  `auto` stats include `palettes_per_shape`; PASS/FAIL per check, exit 0
  only if all pass.
- `python3 scripts/test_mep_compare_render_dispatch.py` - `render_original`
  decodes every supported `<system>` and rejects an unsupported one (or a
  wrong-width palette) before per-tile work; PASS/FAIL per check, exit 0
  only if all pass.
- `python3 scripts/checks/verify_community_pack_issue_template.py` and
  `./scripts/checks/verify_hd_pack_authoring_doc.sh` - see `checks/` above.
- `./scripts/checks/verify_community_pack_labels_script.sh` (AC-2) - see
  `checks/` above.
- `python3 scripts/checks/verify_community_pack_submitted_workflow.py` and
  `python3 scripts/checks/verify_community_pack_validate_workflow.py` —
  F6.0 concurrency / classify-timeout structural checks plus the original
  AC-2/AC-3/AC-6 contracts (see `checks/` above).
- `./scripts/checks/verify_mep_fallback_adr.sh` and
  `./scripts/checks/verify_mep_fallback_adr_provenance.sh` - see `checks/`
  above (AC-7/AC-8 of the MEP zip-fallback task).
- `./scripts/checks/verify_mep_fallback_lint_fixture.sh` and
  `./scripts/checks/verify_mep_fallback_constant_parity.sh` - see `checks/`
  above (AC-5/AC-6 of the MEP zip-fallback task).

## Child DOX Index

- `checks/` - dev-squad/community-pack acceptance-criteria verifiers and
  one-script-one-contract structural checkers (see Work Guidance above); no
  dedicated AGENTS.md yet (a flat collection of independent per-AC
  verifiers with no domain contract of its own beyond what's listed in the
  Work Guidance entry above), promote to a child AGENTS.md if the folder
  grows its own distinct rules.
