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

- `core_unit_tests.cpp` - Fase 4 of the now-completed unit-test plan (see
  git history for `docs/roadmap/plano-testes-unitarios.md`): exercises
  `ChannelRoleClassifier` (role/SFX decisions) and
  `MepPack::NormalizeRelativePath` / `MepPack::Parse` (zip-slip fixture +
  pack.json golden) with no `MesenCore` link at all - the only harness here
  that doesn't need `make core` first.
- `roles_probe.cpp` / `headless_record.cpp` / `spike_sound_driver.cpp` run
  the emulator headless against a real ROM; they link `InteropDLL`'s shared
  lib and need `make core` first.
- `validate-specs.py`, `mep_lint.py`, `mep_compare.py`, `mep_render_audio.py`,
  `gen_hdpack_test_roms.py`, `gen_mep_test_pack.py`, `make_gb_test_rom.py`,
  `validate_hdpack_dump.py` - Python spec/golden/pack validators and
  test-ROM/test-pack generators; no emulator dependency.
- `test_mep_compare_auto_palettes.py` - fixture-based check (writes its own
  small NES-shaped HD pack fixture on disk, no ROM/build dependency) that
  `mep_compare.py`'s `stats["auto"]` dict reports `palettes_per_shape`
  alongside `stats["artist"]`.
- `validate_palette_variants.py` (F5.4b) - builds `headless_record` via
  `make capture-tool` if missing, records `roms/Zelda.nes` with the `hdpack`
  flag, and checks that `HdPackBuilder::ProcessTile` captures more than one
  distinct palette for at least one tile shape while never letting any single
  shape exceed `HdPackBuilder::MaxPaletteVariantsPerTile` (the cap that bounds
  per-shape growth from near-blank/flat tiles - see that constant's comment
  in `Core/NES/HdPacks/HdPackBuilder.h`). Needs `make core`/a real ROM, unlike
  the fixture-only validators above.
- `check-core-manifest.sh`, `check-file-loc.sh`, `verify-fase0-1-dox.sh`,
  `verify-ui-logic-firewall.sh`, `check-f5-4b-doc.sh` - repo-hygiene shell
  checks run from `make` or CI. `check-f5-4b-doc.sh` guards the F5.4b clause
  in `docs/roadmap/plano-execucao-F5.md`'s header Status line: a done (✅)
  marker paired with `F5.4b` and no leftover instance of the pre-fix pending
  phrasing.
- `checks/` - per-deliverable acceptance-criteria verifiers for dev-squad
  runs (one script per AC, invoked directly by its AC's Verification
  command). Same PASS/FAIL-and-exit-code convention as the top-level shell
  checks above; no shared test framework. `checks/verify_claude_md_section.sh`
  guards `CLAUDE.md` (AC-10): the pre-existing "Rastreamento de bugs (GitHub
  Project)" section must stay byte-for-byte untouched (checked as an exact
  file prefix) while a new "Triagem de Community HD/MEP Packs (GitHub
  Project)" section is appended after it.

## Verification

- `make core-unit-tests` - builds and runs `core_unit_tests` (no `core`
  prerequisite); every case must print `PASS` and the binary must exit 0.
- `make roles-probe` / `make capture-tool` / `make spike-sound-driver` -
  each depends on `make core` first.
- `python3 scripts/validate-specs.py` - specs/goldens under `docs/specs/`.
- `python3 scripts/test_mep_compare_auto_palettes.py` - `mep_compare.py`'s
  `auto` stats include `palettes_per_shape`; PASS/FAIL per check, exit 0
  only if all pass.

## Child DOX Index

- `checks/` - dev-squad acceptance-criteria verifier scripts; no dedicated
  AGENTS.md yet (covered by this Work Guidance entry above), promote to a
  child AGENTS.md if the folder grows its own distinct rules.
