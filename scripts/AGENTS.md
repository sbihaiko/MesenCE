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
  git history for `docs/roadmap/plano-testes-unitarios.md`), plus Bloco E
  (ADR-0138 §4/§37, F6.4a): exercises `ChannelRoleClassifier` (role/SFX
  decisions), `MepPack::NormalizeRelativePath` / `MepPack::Parse` (zip-slip
  fixture + pack.json golden), `MepPack::FindFallbackSubfolder` /
  `DetectConventionLayout` (ADR-0120/0121), and (Bloco E)
  `MepRecipeInstaller`/`MepRecipeOps`/`SHA256` against the real-bytes
  fixture under `docs/specs/golden/mep-recipe/fixture/` - a known-answer
  SHA-256 check, a byte-for-byte parity check against
  `python3 scripts/mep_recipe.py apply` on the same fixture (the one case
  here that shells out to a second process), the `apply_patch_only_if_
  complete` transitive-skip withholding a patch while textures still
  install, a sha256 mismatch aborting and writing nothing, and an unknown
  op/recipe version logging `[MEP] recipe unsupported` and skipping. Links
  `Core/Shared/EnhancementPacks/MepPack.cpp` + `MepRecipeInstaller.cpp`/
  `MepRecipeOps.cpp` (the whole interpreter stays these two declared
  units - ADR-0138 §35's file-size-gate exception only applies when a
  task pre-declares the split files in its own file list, which this
  task's did not, so `MepRecipeInstaller.cpp`/`MepRecipeOps.cpp` exceed
  the usual 200-line-per-file guideline rather than growing an
  undeclared sibling file) + `Core/Shared/MessageManager.cpp` +
  `Utilities/{JsonReader,FolderUtilities,
  UTF8Util,sha256,SimpleLock,Timer,miniz}.cpp` directly - no `MesenCore`
  link at all, the only harness here that doesn't need `make core` first.
- `roles_probe.cpp` / `headless_record.cpp` / `spike_sound_driver.cpp` run
  the emulator headless against a real ROM; they link `InteropDLL`'s shared
  lib and need `make core` first.
- `validate-specs.py`, `mep_lint.py`, `mep_recipe.py`, `mep_recipe_assemble.py`,
  `mep_compare.py`, `mep_render_audio.py`,
  `gen_hdpack_test_roms.py`, `gen_mep_test_pack.py`, `gen_mep_fallback_test_pack.py`,
  `gen_mep_recipe_fixture.py`, `make_gb_test_rom.py`, `validate_hdpack_dump.py` -
  Python spec/golden/pack validators and test-ROM/test-pack generators; no
  emulator dependency.
  `mei_rules.py` (F6.3b, ADR-0138 §28/§29) is the dependency-free leaf
  holding the MEI v1.1 constraint set: `SYSTEMS`/`SHA1_UPPER`/`CRC32_UPPER`/
  `MD5_UPPER`/`SHA256_HEX`/`SEMVER`/`MEI_KINDS`, the kind-conditional
  `required_mei_pack_fields(kind)` (a "hd-legacy" pack needs no
  `version`/`mep`; any other kind, including `None`, does -
  docs/specs/MEI-v1.md §2.2/§2.3), and `mei_entry_conforms(entry, kind)`
  (whether an assembled `packs[]` entry already carries a truthy value for
  every field `required_mei_pack_fields` demands - stricter than
  `validate_mei`'s own presence-only check, and unused by
  `mei_catalog_entry.py`'s own same-named function below, which needs
  `rom`'s looser, `validate_mei`-matching semantics; `mei_rules.
  mei_entry_conforms` stays for `test_mei_rules.py`'s own coverage of the
  leaf). It also holds the sole
  Status-literal -> kind pairing in `scripts/` (`STATUS_TO_KIND`, §29) and
  `resolve_kind(mep_meta, status)`, which prefers a valid mep-meta `kind`
  and falls back to `STATUS_TO_KIND.get(status)`, returning `None` (never
  a kind-less resolution) for an unmapped Status with no usable mep-meta
  kind. `validate-specs.py` imports all of the above from this leaf
  instead of defining a second, locally-duplicated copy; its MEI v1.1
  catalog validation (`validate_mei`, `validate_mei_catalog`) is
  otherwise unchanged and stays kind-aware: `rom.sha1` MAY be absent
  regardless of `kind`, and any `deps[]` entry MUST carry `license`.
  `validate_mei_catalog()` runs those rules over the golden and, when
  this checkout has a generated `docs/community-packs.json`, over that
  catalog too. `test_mei_rules.py` is the framework-free acceptance check
  for the leaf (constant shapes, `required_mei_pack_fields`/
  `mei_entry_conforms` per kind, `resolve_kind`'s mep-meta-first /
  Status-fallback / None-when-unmapped precedence).
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
  a zip with a parallel implementation.
  `mep_recipe_assemble.py` (F6.2c, ADR-0138 Clarification §23) holds the
  CI-only `assemble-sources` implementation (issue-body parsing, dep
  merge, its own CLI arg parsing). `mep_recipe_common.py` is the
  dependency-free leaf holding `RecipeError`/`SHA256_HEX`/`RECIPE_VERSION`
  that both import — so there is no import cycle and a direct
  `python3 scripts/mep_recipe.py ...` run never re-executes the CLI under a
  second module name (ADR-0138 §24: splits in `scripts/` break cycles with
  a leaf module, never with lazy in-function imports). `mep_recipe.py`
  re-exports `assemble_sources`/`cmd_assemble_sources` and the three leaf
  symbols as a back-compat facade (test call sites); new code imports the
  assembly helpers from `mep_recipe_assemble` directly. `validate`/
  `dry-run`/`apply` and the dispatch in `main()` never left `mep_recipe.py`.
  `mep_recipe_common.py` also holds the "shortest safe fence" rule
  (F6.3b, ADR-0138 §33): `choose_fence(payload)` picks the shortest
  backtick fence (3 or more) strictly longer than any backtick run
  `json.dumps` (which does not escape backticks) may have left inside
  `payload`, and `find_fenced_block(text, label)` is the matching reader —
  it accepts an opening run of 3+ backticks and matches the closing run
  by that exact same length, never a hardcoded 3-backtick assumption.
  `mep_recipe.py`'s `FENCE` (the ```mep-recipe fence label) and
  `load_recipe` are the CLI-side consumer of the reader half; the writer
  half is meant for any script or CI step that embeds a backtick-fenced
  payload it did not author verbatim (e.g. a submitter-supplied string).
  `test_mep_recipe_fence.py` is the framework-free round-trip proof: a
  payload embedding backtick runs of varying lengths (including a run
  already shaped like a fenced block) survives `choose_fence` +
  `load_recipe` byte-for-byte, the no-backticks case still gets a
  3-backtick fence (no regression), and `load_recipe`'s pre-existing
  "not JSON and no fence" failure mode is unchanged.
  `mep_recipe.py assemble-sources` (F6.2b, ADR-0138 §7/§12/§13) is the
  deterministic step that builds `sources`: it parses the issue body's
  `external_assets` lines (`<url> [<sha256>] [<size>]`, reusing
  `SHA256_HEX` rather than a new regex) and treats every parsed line as
  an authoritative dependency (ADR-0138 §12) — each one becomes a
  `sources.deps` entry regardless of whether classify's `deps[]` has a
  matching item, merging in classify's id/hints/license/user_supplied
  when a `hints` URL matches (trailing slash ignored) and synthesizing
  an id otherwise, so a declared asset is never silently dropped even
  when classify under- or over-counts `deps`.
  `recipe_status` is `absent` when there are no `external_assets` lines,
  or when classify's `ops`/`deps`/`pack` fragment has no actual content
  (schema-required-but-empty containers count as no fragment, ADR-0138
  §7) — never a schema-clean-looking `present` that `validate_recipe`
  would reject; `present` only when a real fragment and well-formed lines
  both exist; `refused` when any line is malformed or missing its
  sha256. Only `present` writes a document (`--out`).
  `test_mep_recipe.py` is the framework-free acceptance check (unknown op
  / escaping path rejected; dry-run of a synthetic split pack is
  `mep_lint`-clean; `assemble-sources`'s absent/present/refused outcomes,
  including an empty-but-present classify fragment, an unmatched
  `external_assets` line surviving into `sources.deps`, and the CLI round
  trip).
  `gen_mep_recipe_fixture.py` (F6.4a) writes the real-bytes MEP-recipe-v1
  golden under `docs/specs/golden/mep-recipe/fixture/` (`primary.zip`,
  `audio-dep.zip`, `recipe.json`, `recipe-missing-dep.json`) that a
  `MepRecipeInstaller`/`mep_recipe.py apply` parity test runs against —
  the pre-existing `docs/specs/golden/mep-recipe/recipe.json` stays
  format-only (its `sha256` fields are the empty string, MEP-recipe-v1
  §9) and is untouched. Each zip is written with a fixed per-entry
  timestamp and STORED compression so re-running the generator reproduces
  the committed bytes exactly (no wall-clock or compressor drift);
  `recipe.json` and `recipe-missing-dep.json` are the identical recipe
  document under two names — the "missing-dep" scenario is exercised by
  omitting the `audio` dep path at apply time, not by a different
  document. The `audio` dep's `size` field is the real on-disk size of
  `audio-dep.zip` (the artifact `sha256` is hashed over, MEP-recipe-v1
  §3.3/§12) — not the sum of its uncompressed entries. The ops include a
  `rename` (`audio/Track 01.ogg` -> `audio/track01.ogg`, the spec's own
  §4.3 example) whose source only the `audio`-dep `glob` produces, so the
  missing-dep scenario also exercises the §6 transitive-skip branch (a
  `rename` reading a withheld path is skipped, not a hard failure).
  `test_gen_mep_recipe_fixture.py` is its framework-free acceptance
  check: the generator's declared `sha256`/`size` fields equal the real
  bytes it writes (never the empty-string placeholder the older golden
  used), the generated documents pass `mep_recipe.validate_recipe`, the
  committed fixture on disk matches its own declared hashes, regenerating
  it into a temp dir reproduces the committed bytes byte-for-byte, and
  running both fixture recipes through `mep_recipe.run_recipe` confirms
  the `rename` actually fires with every dep present and is transitively
  skipped (keeping the patch withheld) when the `audio` dep is missing.
  `mep_meta_parser.py` (F6.3, ADR-0138 §27) is a dependency-free leaf
  exposing a pure `parse_mep_meta(comment_body: str) -> dict | None`: it
  locates the `<!-- mep-meta -->` marker and its fenced ```json block
  written by `community-pack-validate.yml`'s "Upsert mep-meta comment"
  step (no `gh`/network of its own) and decodes it, returning `None`
  instead of raising on any malformed input — missing marker, truncated
  fence, invalid JSON, a non-object JSON payload, or a deeply nested JSON
  payload (which trips `RecursionError`, not `JSONDecodeError`/
  `ValueError`, and is caught explicitly) — so a caller (the F6.3 catalog
  generator) can skip that one entry's recipe data and log a warning
  rather than abort the whole catalog run. `test_mep_meta_parser.py` is
  its framework-free acceptance check (well-formed block round-trips;
  each malformed-input shape above returns `None`; a second fenced block
  later in the comment is never mistaken for the first).
  `generate_community_pack_catalog.py` (F6.3, ADR-0138 §26/§27; split per
  F6.3b/§35 into three files, none over 200 lines) writes
  `docs/community-packs.json` (an MEI v1.1 catalog, `mei: "1.1.0"`) next to
  `docs/community-packs.md` in the same run, and adds an "External assets"
  column to the Markdown table (`yes` when the entry has `deps`) alongside
  the six pre-existing columns. The generator itself is now a thin
  fetch/orchestration facade: `run_gh`/`fetch_accepted_items`/`item_*`/
  `fetch_issue_details`/`fetch_mep_meta_comment_body`/`parse_form_field`/
  `issue_form_fields`/`_build_entry_for_accepted_item`/`main` — per
  accepted board item it fetches the bot-owned `<!-- mep-meta -->` comment
  (`gh api .../comments`, same oldest-by-`sbihaiko` selection
  `community-pack-validate.yml`'s upsert step uses), parses it with
  `mep_meta_parser.parse_mep_meta`, and delegates entry assembly/rendering
  to the two leaves below. It re-exports `build_pack_entry`/
  `mei_entry_conforms`/`normalized_rom_sha1`/`STATUS_MEP_COMPLETO`/
  `STATUS_HD_PARCIAL` as a back-compat facade (ADR-0138 §24, mirroring
  `mep_recipe.py`/`mep_recipe_common.py`) so
  `verify_mei_catalog_generator.py` needed no changes.
  `mei_catalog_entry.py` (F6.3b, new) holds MEI `packs[]` entry assembly,
  depending only on the `mei_rules` leaf (never on `community_pack_
  markdown` or the facade — ADR-0138 §24). `mei_entry_preconditions_ok`
  guards every entry against `validate_mei`'s own constraints before it is
  built: an item missing an HTTPS Pack URL, a well-formed Pack Hash, or a
  Console value with an MEI-representable `system` (the Issue Form's
  first-class "Other" option, and the "?" fallback of a missing/unmapped
  console, have none) gets no JSON entry at all — a warning is logged and
  the Markdown row (tolerant of "?"/"other") is still produced.
  `build_pack_entry` derives `kind` via `mei_rules.resolve_kind` (mep-meta
  `kind` first, the board Status as fallback, §29 — never Status alone)
  and assembles one MEI `packs[]` entry per item, reading `deps[]` from
  mep-meta's embedded `recipe.sources.deps` (never mep-meta's own top-level
  stripped `deps`, which lacks `license`); `kind_from_status` (a facade-
  compatible Status->kind lookup built on `mei_rules.STATUS_TO_KIND`, never
  a second hardcoded pairing) remains for back-compat. `normalized_rom_
  sha1` upper-cases the Project's human-entered "ROM SHA1" field and
  checks its 40-hex shape (reusing `mei_rules.SHA1_UPPER`) before it is
  copied into `rom.sha1`, omitting it on a mismatch. For a `kind == "mep"`
  entry, `build_pack_entry` reads `pack.version`/`pack.mep` out of
  mep-meta's embedded `recipe.pack` (`pack_version_fields`); when the
  recipe is absent/refused and those fields can't be sourced,
  `build_catalog` self-checks every entry through this module's own
  `mei_entry_conforms(entry, kind)` before it is kept (§28) and drops it
  rather than emit one `validate_mei` rejects for missing `version`/`mep`
  — never silently relabeled as `"hd-legacy"` — even if the facade's own
  caller-side check (`entry.get("kind")`) already filtered it.
  `mei_entry_conforms` here is built on `mei_rules.required_mei_pack_
  fields`/`MEI_KINDS` (never a restated field list or kind set) but
  matches `validate_mei`'s (`scripts/validate-specs.py`) real field-by-
  field semantics rather than `mei_rules.mei_entry_conforms`'s stricter
  shortcut: every required field MUST be *present*, and only `rom` is
  exempt from also being non-empty — MEI v1.1 §2.3 makes `rom.sha1`
  MAY-be-absent regardless of `kind`, and `validate_mei` itself checks
  `field in p`, never truthiness, for every field.
  `community_pack_markdown.py` (F6.3b, new) holds the Markdown rendering
  — its "Author" column is mep-meta's `author`, which the classify step
  reads off the pack itself (the Issue Form stopped asking; its old
  `Author/credits` answer is only a fallback for issues that predate the
  change), never the issue login, and `render_table` orders
  rows most-👍-first, which replaced the old `render_popular_section`
  (it re-listed the same packs) along with the Link / Submitted by /
  Category / External assets columns — Link folded into the 👍 cell,
  which links to the submission issue where the vote is cast; `community-pack-validate.yml` seeds one 👍 per
  submission (idempotent reactions API), so a listed pack never sits at
  zero —
  (`escape_table_cell`/`thumbs_up_count`/`console_from_labels`/
  `build_row`/`render_table`/`build_markdown`), stdlib-only since the
  Category column took `mei_rules` with it (and never depending on
  `mei_catalog_entry`); `build_row` takes the caller-derived
  `issue_number`/`status` directly rather than a raw Project item, so it
  never needs the facade's `item_*` helpers.
  `scripts/checks/verify_mei_catalog_generator.py` is the offline, no-`gh`
  checker for the original F6.3 deliverable (AC-2): structural checks
  assert the generator writes `docs/community-packs.json`, uses
  `mep_meta_parser`, derives `kind`, and declares the "External assets"
  column; it also imports the generator's re-exported functions directly
  (no mocks, no live `gh`/`main()` run) to round-trip a `kind == "mep"`
  entry with and without a mep-meta recipe, and a lowercase `rom.sha1`,
  through the real `validate_mei` (`scripts/validate-specs.py`) — it needs
  no edits after the F6.3b split, since the facade still exposes the same
  five names by attribute. `scripts/checks/verify_mei_catalog_split.py`
  (F6.3b, AC-4) is the offline structural checker for the split itself:
  each of the four files is <= 200 lines, `mei_catalog_entry.py` imports
  `mei_rules`, its own `mei_entry_conforms` is built on `mei_rules.
  required_mei_pack_fields`/`MEI_KINDS` (never a restated field list or
  kind set), and it calls `mei_rules.resolve_kind`;
  `community_pack_markdown.py` defines `build_markdown`/`render_table`/
  `build_row`; the facade still exposes the five re-exported names, with
  `gen.mei_entry_conforms` really identical to `mei_catalog_entry.
  mei_entry_conforms` (not a second, facade-local copy); a fully-
  populated entry is still rejected for a kind absent from `mei_rules.
  MEI_KINDS`; and `build_catalog` really does drop a non-conforming entry
  while keeping a conforming one whose `rom` is `{}` (self-check
  behavior, not just text presence).
  `scripts/checks/verify_status_kind_parity.sh` (F6.3b, AC-6, in the
  `verify_mep_fallback_constant_parity.sh` style) asserts the two
  Status-literal -> kind pairs are textually defined exactly once across
  `scripts/` — inside `mei_rules.STATUS_TO_KIND` — and that
  `mei_catalog_entry.py` imports that mapping (`import mei_rules` +
  references `STATUS_TO_KIND`) rather than hardcoding a second, independent
  copy of either pair; fails loudly (names the offending file/count) on
  both a missing pairing and a duplicated one, never vacuously.
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
  (same one-script-one-contract pattern as the checks below). Its 28+
  `check_*` functions live in six topic modules under
  `checks/community_pack_validate/` (a namespace package, no `__init__.py`)
  — `general`, `classify`, `assemble_recipe`, `recipe_gate`,
  `apply_verdict`, `mep_meta` — plus a `_shared.py` holding the common
  `FAILURES`/`fail()` collector every topic module appends to; this file
  itself only loads the workflow, runs the one YAML-shaped check
  (`check_workflow_call_inputs`), imports the topic modules' functions
  into its `CHECKS` tuple, and stays the sole invocation entry point
  (ADR-0138 Clarification §23, F6.2c — a mechanical split, same contract
  as before).
- `check-core-manifest.sh`, `check-file-loc.sh`, `verify-fase0-1-dox.sh`,
  `verify-ui-logic-firewall.sh` - repo-hygiene shell checks. All four are
  now invoked by `make doc-checks` (ADR-0137, roadmap slice H1):
  `check-core-manifest.sh` via the target's `check-manifest` dependency
  (itself still a dependency of `ui`/`core` on its own), then
  `verify-fase0-1-dox.sh`, `verify-ui-logic-firewall.sh`,
  `check-file-loc.sh` (against `Core/Shared/Audio/MidiExporter.cpp 200`),
  and the ADR-0138 §41 F6.4b-2 trio -
  `checks/verify_pack_host_allowlist_embed.sh`,
  `checks/verify_core_no_http_client.sh`, and
  `checks/verify_fetcher_no_filesystem_allowlist_load.sh` (see `checks/`
  below) - run directly by `doc-checks`, in order, failing on the first
  non-zero exit. CI runs `make doc-checks` as its own step on the Linux
  and macOS build jobs, before "Build Mesen". `check-f5-4b-doc.sh` was
  deleted on 2026-08-27 together with the plan header it guarded.
- `checks/` - per-deliverable acceptance-criteria verifiers for dev-squad
  runs (one script per AC, invoked directly by its AC's Verification
  command). Same PASS/FAIL-and-exit-code convention as the top-level shell
  checks above; no shared test framework. `checks/verify_claude_md_section.sh`
  guards `CLAUDE.md` (AC-10): the pre-existing "Rastreamento de bugs (GitHub
  Project)" section must stay byte-for-byte untouched (checked as an exact
  file prefix) while a new "Triagem de Community HD/MEP Packs (GitHub
  Project)" section is appended after it. `verify_community_pack_issue_template.py`
  parses `.github/ISSUE_TEMPLATE/community-pack.yml` with PyYAML and asserts
  the required fields/labels/doc-link, plus (ADR-0138 §12) that the optional
  `external_assets` textarea and `external_assets_license` input exist, are
  not required, and that `external_assets`'s description documents the
  `<url> [<sha256>] [<size>]` per-line grammar. `verify_hd_pack_authoring_doc.sh`
  checks that `docs/hd-pack-authoring.md` exists, is non-trivial, cites
  `docs/specs/MEP-v1.md` §5.1/§5.2/§5.3/§6, and documents the
  split-distribution/MEP Recipe flow (ADR-0138 §12): the
  "Split-distribution packs (MEP Recipe)" section, `external_assets`,
  `assets:external`, and a citation of `docs/specs/MEP-recipe-v1.md`.
  `verify_community_pack_labels_script.sh`
  (AC-2, ADR-0138 F6.2a) parses the `LABELS` array of
  `ensure_community_pack_labels.sh` literally (not one representative grep)
  and asserts both the exact 12-entry count and the full expected name set,
  including the `assets:external` content-index label.
  This is the standing shape for verifiers of array-shaped config (ADR-0035
  made concrete): extract the entries from the source array, assert an
  explicit expected name set kept *outside* the target (deriving the names
  from the target would make the check tautological), and derive the count
  from that set (`${#EXPECTED_NAMES[@]}`) — never a magic integer.
  `verify_mep_fallback_constant_parity.sh` is the cross-file exemplar.
  `verify_agents_md_recipe_handoff.sh` (AC-4, F6.2a) checks that
  `.github/AGENTS.md` documents the ADR-0138 §13 recipe handoff: the
  `$RUNNER_TEMP/mep_recipe.json` path (and prose stating it is runner-local
  and never written inside the checkout) plus the three-valued
  `recipe_status` step output (`absent`/`present`/`refused`); it never
  touches a workflow file — the assembly step itself is F6.2b.
  `verify_community_pack_submitted_workflow.py`,
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
  Bloco E's parity case shells out to `python3 scripts/mep_recipe.py apply`
  (a `python3` on `PATH` is required to run this target, unlike every other
  Bloco here).
- `make roles-probe` / `make capture-tool` / `make spike-sound-driver` -
  each depends on `make core` first.
- `python3 scripts/validate-specs.py` - specs/goldens under `docs/specs/`.
- `python3 scripts/test_mei_rules.py` (F6.3b) - `mei_rules.py` leaf: constant
  shapes, `required_mei_pack_fields`/`mei_entry_conforms` per kind,
  `resolve_kind`'s mep-meta-first / Status-fallback / None-when-unmapped
  precedence; PASS/FAIL per check, exit 0 only if all pass.
- `python3 scripts/test_mep_recipe.py` - MEP Recipe v1 interpreter
  (unknown op / escaping path rejected; synthetic split-pack dry-run is
  `mep_lint`-clean) plus `assemble-sources` (absent/present/refused per
  ADR-0138 §7/§13, CLI round trip); PASS/FAIL per check, exit 0 only if
  all pass.
- `python3 scripts/test_gen_mep_recipe_fixture.py` (F6.4a) -
  `gen_mep_recipe_fixture.py`'s hash-correctness check: declared
  `sha256`/`size` fields equal the real bytes written (never the
  empty-string placeholder, never a size that isn't the artifact's own
  on-disk size), generated documents pass `mep_recipe.validate_recipe`,
  the committed `docs/specs/golden/mep-recipe/fixture/` matches its own
  on-disk bytes, regenerating it is byte-identical, and applying both
  fixture recipes through `mep_recipe.run_recipe` confirms the `rename`
  op fires (full deps) and is transitively skipped (missing dep, §6);
  PASS/FAIL per check, exit 0 only if all pass.
- `python3 scripts/test_mep_recipe_fence.py` (F6.3b, AC-7/AC-9) - the
  ADR-0138 §33 "shortest safe fence" round trip: `choose_fence` +
  `mep_recipe.py`'s `FENCE`/`load_recipe` recover a backtick-laden
  payload byte-for-byte, the no-backticks case still gets a 3-backtick
  fence, and `load_recipe`'s pre-existing failure mode is unchanged;
  PASS/FAIL per check, exit 0 only if all pass.
- `python3 scripts/test_mep_meta_parser.py` - `mep_meta_parser.parse_mep_meta`
  (F6.3, ADR-0138 §27): well-formed `<!-- mep-meta -->` block round-trips;
  missing marker, truncated fence, invalid JSON, a non-object JSON
  payload, and a deeply nested JSON payload (`RecursionError`, not
  `ValueError`) all return `None` without raising; PASS/FAIL per check,
  exit 0 only if all pass.
- `python3 scripts/checks/verify_mei_catalog_generator.py` (AC-2, F6.3) -
  offline structural checker for `generate_community_pack_catalog.py`'s
  JSON-catalog/`kind`/External-assets-column additions; see `checks/`
  above.
- `python3 scripts/checks/verify_mei_catalog_split.py` (AC-4, F6.3b) -
  offline structural checker for the `mei_catalog_entry.py`/
  `community_pack_markdown.py`/facade split; see `checks/` above.
- `./scripts/checks/verify_status_kind_parity.sh` (AC-6, F6.3b) - the
  Status->kind pairing is defined exactly once, in
  `mei_rules.STATUS_TO_KIND`; see `checks/` above.
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
- `./scripts/checks/verify_pack_host_allowlist_embed.sh` (ADR-0138 §41,
  F6.4b-2, AC-17/AC-18) - asserts `UI/UI.csproj` embeds
  `scripts/pack_host_allowlist.json` as an `EmbeddedResource` with the
  exact `Include="../scripts/pack_host_allowlist.json"` and
  `LogicalName="Mesen.pack_host_allowlist.json"` pair on the same
  element - the only handle `CommunityPackCatalogFetcher` has for the
  allow-list once packaged, since a published app has no `scripts/` tree.
- `./scripts/checks/verify_core_no_http_client.sh` (ADR-0138 §37, F6.4b-2,
  AC-20) - asserts `Core/` never grows real HTTP-client code
  (`#include <curl/...>`, `curl_easy_*`, `CURLOPT_*`, a `CURL*` handle, or
  an `HttpClient` identifier); strips `//` and `/* */` comments line-for-
  line first so a prose mention (e.g. `MepRecipeInstaller.h`'s own "no
  HTTP, no libcurl" disclaimer) is never mistaken for a violation - the
  network boundary stays entirely inside `UI/Services/`.
- `./scripts/checks/verify_fetcher_no_filesystem_allowlist_load.sh`
  (ADR-0138 §41 PRIORITY 1, F6.4b-2, AC-8) - asserts
  `UI/Services/CommunityPackCatalogFetcher.cs` never references
  `LoadFromFile` or a repo-relative-path literal for the allow-list.

## Child DOX Index

- `checks/` - dev-squad/community-pack acceptance-criteria verifiers and
  one-script-one-contract structural checkers (see Work Guidance above); no
  dedicated AGENTS.md yet (a flat collection of independent per-AC
  verifiers with no domain contract of its own beyond what's listed in the
  Work Guidance entry above), promote to a child AGENTS.md if the folder
  grows its own distinct rules.
