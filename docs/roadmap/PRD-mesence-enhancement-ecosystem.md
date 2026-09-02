# PRD — MesenCE roadmap

Consolidated roadmap of the MesenCE fork. This single document unifies the
former two PRDs — `PRD-mesence-enhancement-ecosystem.md` (pack/core) and
`PRD-player-shell.md` (default GUI / chrome) — into two Parts of one file
(2026-08-30, per the project owner's decision). Each Part keeps its own
internal `§N` numbering verbatim; a `§N` reference always resolves within
the Part that uses it. The former ownership split still holds — pack/core
work lives in Part A, player-shell/chrome work lives in Part B — it is now
expressed as parts of one file instead of two files.

Part A is the pack/core roadmap: vision and legal principles, standards,
the shipped record, and the pending slices (Phase 5/6, repo hygiene, input
tester, Phase 8 border layer). Part B is the default-GUI roadmap: player
chrome, Advanced GUI, pack identity (`pack_id`/`content_id`/version),
duplicates, the pack picker, and the quick-enhancements panel. The two
Parts intentionally do not duplicate each other's prose: each holds its own
header block, slice table, and ADR map.

---

## Part A — Enhancement ecosystem (pack/core)

**Status:** active (2026-09-01) — pack/core roadmap of this fork. Player
chrome, pack identity (`pack_id`/`content_id`/version) and the in-GUI
picker live in Part B of this document (Phase 7).
Earlier plans (`PRD-ecossistema-enhancement-comunitario.md`,
`PRD-community-pack-mep-conversion.md`, `plano-execucao-F3.md`,
`plano-execucao-F5.md`, `plano-reducao-consoles.md`,
`plano-host-input-tester.md`) were consolidated here and deleted on
2026-08-27; their full text lives in git history. ·
**Author:** sbihaiko ·
**Scope:** MesenCE fork (`main`); nothing goes upstream ·
**Specs:** [MEP-v1](../specs/MEP-v1.md) · [MEI-v1](../specs/MEI-v1.md) · [ESP-v1](../specs/ESP-v1.md) · [MEP-recipe-v1](../specs/MEP-recipe-v1.md) · [hires-gbsms-v1 (draft)](../specs/hires-gbsms-v1-draft.md) ·
**Decisions:** `.dev-squad/adr/` — `accepted` ADRs are binding; §6 lists the ones this roadmap depends on ·
**Process:** one dev-squad run per **slice** (F6.1, F6.2, …), never a whole phase or the whole PRD in one run — the decompose step failed twice when fed multi-phase work. Settle the slice's ADRs before running it. A slice is done when its acceptance checks pass headless and the header of this file is updated.

---

### 1. Vision and legal principles

MesenCE turns the emulator into a **platform for extracting, authoring and
consuming enhancement packs** (textures, replacement audio, synth presets),
with the community producing the content and the project staying legally
clean. The reference for the thesis is SUPER ZSNES's per-game curated
enhancements; the difference is that everything here is open (CC0 specs,
GitHub as backend, no server).

Principles that every phase below obeys:

1. **Distribute the tool, never the files.** Extractors and installers are
   ours; extracted MIDIs, tiles and third-party redrawn textures stay on the
   user's machine or in the hubs that already host them.
2. **The official channel carries only clean data:** specs, hash mappings,
   presets, catalogs (URLs + hashes + licences), tools. Derivative content
   is *referenced*, never hosted or committed.
3. **The emulator is content-dumb:** no bundled derivative material, no P2P,
   no monetisation (*MGM v. Grokster*, Yuzu 2024).
4. **Hosts never execute pack content as code** (MEP-v1 §6). Patches and
   recipes are declarative data interpreted by a fixed vocabulary.
5. **No LLM in the client.** LLMs run only in CI (the community-pack classify
   step); whatever they emit is validated by deterministic scripts before a
   human or the client sees it.

Product consoles on `main`: **NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA**. SNES
(incl. Super Game Boy), PC Engine, WonderSwan and ColecoVision were removed
on 2026-08-26 (`master` is the frozen full-console snapshot; never merge
`upstream/master` into `main`). SNES **gamepads** (`SnesController`) stay as
host/console input devices. MSU-1 left with the SNES core.

### 2. Standards

Rule: adopt an existing standard when one exists; write an open spec (CC0,
RFC 2119, semver, golden file, `scripts/validate-specs.py`) only for what
does not exist.

| Area | Standard | Status |
|---|---|---|
| ROM identification | No-Intro sha1 (iNES header-size normalisation, ADR-0039/0044) | shipped |
| Textures | HDNes `hires.txt` (Mesen is the reference implementation) | shipped, NES/GB/SMS |
| NES replacement audio | OGG via HD pack `<bgm>/<sfx>` + APU fingerprint trigger (ADR-0047) | shipped |
| Patches | IPS/BPS in `patches[]` by sha1 (ADR-0044) | shipped |
| Audio log / score | VGM 1.71 + GD3, SMF type 1 + GM | shipped (F1) |
| **ESP v1** — Enhanced Synth Preset | `docs/specs/ESP-v1.md` | v1 |
| **MEP v1** — pack container | `docs/specs/MEP-v1.md` (§2.1 folder-form, sibling folder, `auto/` layer; §3 `pack.json` optional; §4 hash; §5 sections; §6 security) | v1.3 |
| **MEI v1** — discovery index | `docs/specs/MEI-v1.md` (federated `manifest.json`) | v1.3 (Phase 6 made it real as v1.1; D3 v1.2 `rom.sha1s`, D13 v1.3 `pack_id`/`content_id`/`votes`, all additive) |
| hires.txt extension GB/SMS (OGG on GB/SMS) | `docs/specs/hires-gbsms-v1-draft.md` | draft, frozen until a second implementer appears |
| **MEP Recipe v1** — re-packaging of split-distribution packs | `docs/specs/MEP-recipe-v1.md` | v1 |

### 3. What has shipped (record, one line each)

- **F1 — MIDI/VGM exporter** from the Enhanced Synth tap; headless harness
  (`scripts/headless_record`) records without GUI.
- **F2 — HD Pack Builder for GB/SMS** (ADR-0036/0037); loader/renderer 1:1.
- **F3 — MEP v1 host** (ADR-0038…0042): folder + zip packs, hash matching,
  per-section toggles, "Enhancement Packs" window, golden tree; zips are
  extracted to `.cache`; lexicographic precedence between packs.
- **Console reduction** (2026-08-26): `main` = NES/GB/SMS/GBA.
- **F5.1 — convention over configuration** (ADR-0044/0049): sibling folder
  `<ROM>/` = pack, `auto/` = machine layer, human > `auto/`; `patches[]`;
  `scripts/mep_lint.py`; discovery precedence sibling > `HdPacks/<Game>/` >
  `EnhancementPacks/` (ADR-0040 as revised by 0049, extended by 0120/0121).
- **F5.2 — image bootstrap** (`BootstrapEnhancementFolder`, xBRZ 4x into
  `auto/textures/`, ROM/PRG-scan tile export incl. CHR-RAM games, ADR-0043).
- **F5.3 — sound bootstrap**: `NesAudioBootstrap` → `TrackSegmenter` →
  `fingerprints.json` + seed MIDI; `mep_render_audio.py`; `NesAudioReplacer`
  swaps OGG in by fingerprint (ADR-0047).
- **F5.4a/a′ — `<background>` screens** (ADR-0050) and assets-without-playing.
- **F5.4b — per-shape palette-variant cap** (ADR-0132; follow-ups (a) saturation
  log and (b) seed-from-disk shipped 2026-08-29).
- **F5.4f spike — sound-driver discovery** (`scripts/spike_sound_driver`,
  ADR-0051 → runtime contract ADR-0135).
- **F5.4g Block A — level-2 audio**: `ChannelRoleClassifier`, SFX separation,
  TinySoundFont GM cover, `roles_probe` (ADR-0052).
- **Community-pack pipeline**: Issue Form → `community-pack-validate.yml`
  (host allow-list, `mep_lint.py`, sha256 → board "Pack Hash", LLM classify
  with a binary verdict, labels `pack:*`/`assets:*`/`patch:*`/`console:*`),
  `/revalidate`, daily drift check, `docs/community-packs.md` catalog.
  Legacy bare `hires.txt` packs (incl. GitHub `/archive/` wrappers) are
  accepted via the structural fallback of ADR-0121 (option A, shipped
  `805cb10d`).
- **Unit tests / CI**: `UI.Tests` + core unit tests (ADR-0122, 0126, 0127,
  0129, 0130).
- **H1 — `make doc-checks`** (ADR-0137): wires `check-core-manifest.sh`,
  `verify-fase0-1-dox.sh`, `verify-ui-logic-firewall.sh`, and
  `check-file-loc.sh` (against `Core/Shared/Audio/MidiExporter.cpp`, 200
  lines) into one `make` target that the Linux and macOS `build.yml` jobs
  run before their build step.
- **H2 — `unit-tests.yml` contract as invariants** (ADR-0131): the
  `.github/AGENTS.md` Work Guidance bullets state what the workflow must
  never do (link `InteropDLL`/`MesenCore`, need SDL2/SDK/ROMs), note that the
  `ui-tests` job covers both host-free suites, record the clang-only C++
  step and the `10.x` dotnet pin, with grep lines in Verification. Doc-only;
  the workflow file was already compliant.
- **H3 — `path-cases.txt` format guard and control-char scope** (ADR-0124):
  `validate_path_cases` in `scripts/validate-specs.py` (skip rules identical
  to the C++ reader, no whitespace around the path column), a "Scope" note in
  the fixture header, and `TestNormalizeRelativePathRejectsControlChars` in
  `scripts/core_unit_tests.cpp` Block B (NUL, 0x01, literal TAB).
- **F6.0 — community-pack pipeline prerequisites** (ADR-0138):
  `community-pack-submitted.yml` `cancel-in-progress` is gated on
  `issues` events so a verdict comment no longer cancels the catalog
  dispatch; classify step `timeout-minutes: 15`; catalog backfill of
  accepted packs #64 and #73.
- **F6.1 — MEP Recipe v1 spec + interpreter** (ADR-0138):
  `docs/specs/MEP-recipe-v1.md`, golden `docs/specs/golden/mep-recipe/recipe.json`,
  MEP-v1 §6 "as code" wording and §2.1 rule 9 bare-basename (ADR-0121),
  `scripts/mep_recipe.py validate|dry-run|apply` reusing `mep_lint`
  discovery.
- **F6.2a — issue metadata + docs half of F6.2** (ADR-0138 §12–14, run
  `4f0d742630e5`): Issue Form `external_assets` textarea (grammar of §12)
  and `external_assets_license` input; `assets:external` label in
  `ensure_community_pack_labels.sh`; "Split-distribution packs (MEP Recipe)"
  section in `docs/hd-pack-authoring.md`; §13 handoff
  (`$RUNNER_TEMP/mep_recipe.json` + `recipe_status`) recorded in
  `.github/AGENTS.md` Local Contracts; verifiers
  `verify_community_pack_labels_script.sh`,
  `verify_agents_md_recipe_handoff.sh` and extended Issue-Form/authoring-doc
  checks. F6.2b (workflow steps) is the remaining half.
- **F6.2b — workflow half of F6.2** (ADR-0138 §1–2, §4, §6–7, §9–13,
  §16–23, run `3cca17a3180c` + follow-up): classify schema carries the recipe
  as one optional nested `recipe` fragment; `assemble-recipe` step
  (`mep_recipe.py assemble-sources`, issue body via `gh issue view`,
  `$RUNNER_TEMP/mep_recipe.json`, `recipe_status` enum, `continue-on-error`);
  `recipe-gate` (validate + dry-run → `recipe_ok`); `apply-verdict` sole
  verdict writer (single downgrade expression, `assets:external` branch,
  `refused` note, `verdict`/`labels` outputs); wholesale `<!-- mep-meta -->`
  upsert with provenance line and `recipe_ok`; `run_recipe` transitive skip
  of dep-dependent `rename`/`rewrite-paths` (MEP-recipe-v1 §6 amended);
  `verify_community_pack_validate_workflow.py` CHECKS extended. F6.2 done;
  **F6.2c** (mechanical split, §23) precedes F6.3.
- **F6.2c — mechanical split** (ADR-0138 §23–24, run `05a8927950be` +
  follow-up): `scripts/mep_recipe_assemble.py` (CI-side assembly) and leaf
  `scripts/mep_recipe_common.py`; `verify_community_pack_validate_workflow.py`
  is a 121-line entry point assembling `CHECKS` from six topic modules under
  `scripts/checks/community_pack_validate/`. Behaviour unchanged; all tests
  and verifiers green.
- **F6.3 — catalog as MEI v1.1** (ADR-0138 §3, §18, §25–27, run
  `3630fa06cbcf`, 2026-08-28): `generate_community_pack_catalog.py` also
  writes `docs/community-packs.json` (`mei: "1.1.0"`, one entry per accepted
  item from Project fields + Form fields + mep-meta; `kind` mep/hd-legacy;
  non-conformant items omitted with a warning); `scripts/mep_meta_parser.py`
  pure parser + tests; MEI-v1 amended to v1.1 (kind, optional rom.sha1,
  deps/recipe, provenance fields) with golden bumped; `validate-specs.py`
  gains `validate_mei_catalog()`; catalog workflow commits both files;
  Markdown gains "External assets" column. Follow-up (same day): `license`
  made optional across MEP/MEI/lint/validator/`MepPack.cpp` (§34); auditor
  findings folded into §28–§35; F6.3b hardening slice defined.
- **F6.3b — catalog hardening** (ADR-0138 §28/§29/§33/§35, run
  `0613b444cee2`, 2026-08-28): leaf `scripts/mei_rules.py` (constants,
  `required_mei_pack_fields`, `mei_entry_conforms`, `STATUS_TO_KIND`,
  `resolve_kind`) shared by `validate-specs.py` and the generator; generator
  split into `mei_catalog_entry.py` + `community_pack_markdown.py` with a
  ≤200-line facade; `apply-verdict` writes `kind` into mep-meta; shared
  fence rule (`choose_fence`/`find_fenced_block` in `mep_recipe_common.py`)
  used by the mep-meta writer, `mep_recipe.py` and — fast-follow —
  `mep_meta_parser.py`; second `mei_entry_conforms` removed (fast-follow);
  checkers `verify_mei_catalog_split.py`, `verify_status_kind_parity.sh`,
  tests `test_mei_rules.py` and fence round-trips. §36 process lesson.
- **F6.4a — Core offline recipe installer** (ADR-0138 §4, §37, run
  `99c183d691f7`, 2026-08-28): `Utilities/sha256.{h,cpp}` (self-contained,
  `""` on unopenable file); `Core/Shared/EnhancementPacks/MepRecipeInstaller.{h,cpp}`
  + `MepRecipeOps.{h,cpp}` — offline four-op interpreter, sha256 gate,
  §6 transitive skip, `pack.json` + `.mep-install.json`, `[MEP] recipe
  unsupported` on unknown op/version; `AutoInstallCommunityPacks` appended
  to `EnhancementPackConfig` (C++ and C# interop struct in lockstep);
  real-bytes fixture `docs/specs/golden/mep-recipe/fixture/` from
  `gen_mep_recipe_fixture.py`; `core_unit_tests` Bloco E: C++ install equals
  `mep_recipe.py apply` byte-for-byte (79/79). Run ended `ac_failed`/T4
  stagnated on critic false positives; T4 recovered from the orphaned branch
  and merged by hand (§40). Audit folded into §35, §38–§40.
- **F6.4b — UI fetch + consent** (ADR-0138 §37/§38/§41–§55, runs
  `2ef26ba839d1` + `119e1031a25f`, 2026-08-28): host-free decision classes
  `UI/Logic/Community{PackHostAllowlist,CatalogCacheDecision,PackDepResolver,
  PackReinstallDecision,PackConsentState,PackCatalog,PackContainerName}.cs`
  (UI.Tests 183/183); `InteropDLL/EmuApiWrapperMep.cpp` `InstallMepRecipe`
  export + `EmuApi` DllImport; `UI/Services/` layer —
  `CommunityPackDownloader` (§50: per-hop allow-list, no auto-redirect,
  byte cap), `CommunityPackCatalogFetcher` (ETag cache, No-Intro sha1
  match, sha256-verified `.cache/downloads/`), `CommunityPackInstallCoordinator`
  (§43 reinstall gate, dep resolution, `id<TAB>path` rows → interop),
  `CommunityPackInstallService` (ROM-load hook, §51 consent-before-network,
  per-session idempotency, withheld-patch / user_supplied notices);
  allow-list embedded in `UI.csproj` (§41) with three `scripts/checks/`
  guardrails in `make doc-checks`; `AutoInstallCommunityPacks` checkbox +
  first-run consent dialog in `EnhancementPacksWindow`; firewall script now
  enforces the §53 three-layer rule both ways. Both runs ended `ac_failed`
  with T1 stagnated; recovered per §40. GUI flow not yet exercised against
  the live catalog (needs F6.5's re-validated entries).
- **F6.4c — parity fixture set** (ADR-0138 §39; run `cdcf29816ecd` stalled at
  Spec on spec-proxy context thrashing — the dev-squad's own spec document,
  `validation.pass: true`, was implemented by hand following the same slice):
  `gen_mep_recipe_fixture.py` gains the shared `ROM_NAME` constant and the
  three discovery edge-case primaries — `wrapped-subfolder.zip` (ADR-0120
  name-anchored subfolder), `nested-zip.zip` (nested top-level zip, sha256 of
  the outer container) and `bare-probe.zip` (ADR-0121 bare `preset.cfg`
  probe) — each with its own `recipe-<case>.json` reusing the shared
  `audio-dep.zip`; `test_gen_mep_recipe_fixture.py` iterates the full set
  (`rom_name` threaded into the wrapped cases, non-empty-tree assertion);
  Bloco E grows the table-driven `TestDiscoveryEdgeCaseParity` passing the
  identical non-empty `romName` to both interpreters (or `""` for nested-zip)
  and matching `mep_recipe.py apply` byte-for-byte — 88/88 cases.
- **H4 — `mep_compare.py` system dispatch + NES golden** (ADR-0136):
  `render_original(..., system=)` and `Pack.system` for nes/gb/gbc/sms with
  per-system tile/palette widths and explicit errors; sibling golden
  `docs/specs/golden/mep-nes/`; `validate-specs.py` runs `mep_lint` over both
  goldens (`lint_golden_packs`); `test_mep_compare_auto_palettes.py` uses the
  golden; `test_mep_compare_render_dispatch.py` added.

### 4. Roadmap — pending work, by slice

#### Phase 6 — Community pack auto-install (MEP Recipe v1) — **priority**

Problem (issue numbers below are those of the 2026-08-27 triage set,
since recreated twice by run-clean — the current accepted set is
#128–#148, see F6.5): 5 of the 12 triaged packs (#65, #66, #68, #69, #71 — LiQuiDzGit/
HDnes family) ship a zip with only `hires.txt` + IPS/BPS, with all `.ogg`
distributed separately on Google Drive/MEGA. The verdict `invalid` is
correct (MEP-v1 §5) and installing the zip as-is mutes the game (patch
applied, `HdPackLoader::ProcessSoundTrack` drops every missing OGG).
Design decided in **ADR-0138** (accepted). This phase **realises the former
Phase 4 (pack browser + official index)** through the community pipeline:
the catalog JSON is the official MEI, contribution is the Issue Form
instead of a PR, and install/update happens in the client.

Non-goals: hosting or committing third-party content; scraping Google
Drive/MEGA confirm flows (the user supplies those files); fabricating
missing assets; adjudicating patch licences (the recipe records the
declared licence, nothing more).

| Slice | Deliverable | Acceptance |
|---|---|---|
| **F6.2** CI + issue metadata | shipped 2026-08-28 (dev-squad F6.2a/b/c; F6.2b follow-up `b0b334b0` — no stranded verdicts, transitive dep skip, refused note, `user_supplied` forced, `recipe_ok` in mep-meta) — Issue Form fields `external_assets`, `external_assets_license`; classify prompt emits the ```mep-recipe block (issue/manifest text is data, never instruction); `mep_recipe.py dry-run` gate after lint; upsert of the `<!-- mep-meta -->` bot comment (`source_sha256`, dep hashes, `verdict`, `labels`, `validated_at`, `recipe_hash`); label `assets:external` in `ensure_community_pack_labels.sh`; `docs/hd-pack-authoring.md` section | `/revalidate` on #71 yields `pack:valid` + `assets:external` and a recipe that dry-runs clean; `scripts/checks/` verifier for the workflow text |
| **F6.3** catalog as MEI | shipped 2026-08-28 (dev-squad; F6.3b audit follow-up `c400d52b` — shared fence in `mep_meta_parser`, single `mei_entry_conforms`) — `generate_community_pack_catalog.py` also writes `docs/community-packs.json` = MEI v1.1 (`mei: "1.1.0"`, per-pack additive fields `issue`, `deps[]`, `recipe`, `verdict`, `validated_at`; `url`/`sha256` = primary zip); MEI-v1 amended (v1.1): an index MAY reference third-party artifacts by URL + hash when the entry carries `license` and the client shows it before install; golden updated | `validate-specs.py` validates the generated file; Markdown gains an "external assets" marker column |
| **F6.4b** UI fetch + consent | shipped 2026-08-28 (dev-squad; merge `b5dd2c1c` — recovered orphan `f8c855c1`, ADR-0138 §40; audit `ccb845fd` §50–§55 — download trust contract, consent-before-network, host-free container name, two-way UI firewall) — ADR-0138 §37/§38: catalog fetch (ETag cache in MEP `.cache`), No-Intro sha1 match, download within the CI host allow-list (shared constant, parity-checked), sha256 verify, downloads-cache lookup, prompt for `user_supplied` deps with hints + licence, settings toggle + first-run consent for `AutoInstallCommunityPacks`, interop call into `MepRecipeInstaller`, reinstall on `source.sha256` change, UI notice when the patch is withheld | UI.Tests for allow-list/ETag/consent logic under `UI/Logic/`; manual GUI pass |
| **F6.4c** parity fixture set | shipped 2026-08-28 — ADR-0138 §39: grow `gen_mep_recipe_fixture.py` to wrapped-subfolder, nested top-level zip and ADR-0120/0121 fallback cases; Bloco E iterates the set | all cases byte-for-byte |
| **F6.4** (original row, superseded by F6.4a/b/c — all shipped 2026-08-28) | `MepRecipeInstaller` (Core, F6.4a): fetch catalog (ETag cache in the MEP `.cache`), match ROM by No-Intro sha1, download primary within the CI host allow-list, verify sha256, prompt for `user_supplied` deps with hints + licence, run ops, write `pack.json` + `.mep-install.json`; reinstall when `source.sha256` changes; setting `AutoInstallCommunityPacks` (default on for packs without user-supplied deps; prompt otherwise); UI notice when the patch is withheld | headless: synthetic catalog + split pack → installed folder equals `mep_recipe.py apply` output byte-for-byte; hash mismatch aborts; missing dep → no patch, textures still applied |
| **F6.5** rollout | shipped 2026-08-29 — re-validated all 11 approved packs (run-clean: old issues deleted; a second run-clean recreated the set as **85–95**; a third run-clean recreated it as **#128–#148**, the current accepted set — 2026-08-30/31, validated locally in parallel via `scripts/validate_pack_local.sh` + the `.github/ai/validate-classify.md` prompt family); classify headless fixed (model, stdin prompt, `--output-format text`, empty `--mcp-config`), ops schema tightened (oneOf), console label added; CI single source (ADR-0138): `community-pack-validate.yml`'s `prepare-classify-prompt` step renders `.github/ai/validate-classify.md` (rsplit extraction + `{{ISSUE_NUMBER}}`/`{{EXTERNAL_ASSETS_SUFFIX}}` placeholders) into `classify_prompt`/`classify_schema` step outputs, and the "Classify pack" step consumes those — no inline schema copy left to drift (schema-contract checks now read the .md SCHEMA block) | all eleven `pack:valid` + `console:nes` + `assets:*`/`patch:*` labels; board "Aceito parcial (HD Mesen)"; 88/89/91/92 = LiQuiDz split-distribution audio (`assets:external` + MEP recipe dry-runs clean); catalog regenerated 2026-08-29 (MEI now populated — the board-accessor key-casing bug fixed; one live slot per `pack_id` per ADR-0141 collapsed the six `liquidzgit/hdnes` submissions to a single slot — Duck Hunt at the time; resolved by **ADR-0143** (`pack_id` = origin × game, multi-game zips expand into `pack:split` sibling issues). On 2026-08-31 the eight audio-only NEA siblings sharing the whole-repo zip (#128–#131, #133–#136; still `pack:valid`) were removed from the catalog and closed — the pinned sha256 of the shared zip went stale, so the download never verified and the packs never applied (commits `fd244f2a`, `7bc8f13a`; rationale only in the issue comments — ADR-0148, slice D4, 2026-09-01). Only Ice Climber #132 of that family is listed today); `verify_community_pack_validate_workflow.py` + `make doc-checks` green; GUI end-to-end install with user-supplied audio still pending; CI live validation re-enable (`LIVE_VALIDATION_ENABLED` → `'true'`, which also arms the autofix-PR step) deferred by user decision 2026-08-29 |
| **F6.6** headless load smoke | shipped 2026-08-29 — `scripts/smoke_pack_headless.sh <installed-pack-dir> <rom>`: boot the headless core (the F1 `scripts/headless_record` binary, no GUI) with the ROM and the installed pack loaded (bootstrap convention — pack folder as sibling of the ROM), capture the HdPackLoader / audio-loader log; assert zero missing-target warnings for any `<img>`/`<tile>`/`<background>`/`<bgm>`/`<sfx>` target the manifest references. Texture packs must tick frames; audio packs must register every declared track. The ROM is a user-supplied No-Intro image (never redistributed) or a homebrew test ROM for CI; `user_supplied` external audio (e.g. the LiQuiDz OGGs) is smoked only when the audio is supplied locally, otherwise reported as skipped — this is the runtime half of "installed end-to-end", making it automatable where the GUI pass stays manual for audio *content* | `scripts/checks/verify_smoke_pack_headless.sh` wired into `make doc-checks` (CI variant boots a synthetic NROM over the F6.4c fixture packs, missing-dep case SKIPs): 5/5 cases green; the gate loop rejects missing img PNG, `<background>`, bad bitmap index, corrupt PNG, `no loadable hires.txt` and (absent `--allow-missing-audio`) missing OGG; round-trip fix shipped with it — `MepPack::Parse` now accepts an empty section `path` (= the pack root, MEP-v1 §3.2) via `RequireSectionPath`, so recipe-installed packs with root-level sections load (`core_unit_tests`: +6 empty-path cases, 50 PASS/0 FAIL) |
| **F6.7** auto-load every accepted pack (ADR-0146) | decided 2026-09-01, core shipped 2026-09-01 — the first-run consent gate no longer blocks auto-install: `CommunityPackConsentState.Evaluate` ignores `CommunityPackAutoInstallConsentGiven` (`AutoInstallCommunityPacks` is the single master switch), consent tests + UI/Logic firewall updated. Consent plumbing removed 2026-09-01 (slice D6: `CommunityPackConsentState`, `CommunityPackAutoInstallConsentGiven`, the `EnsureCommunityPackAutoInstallConsent` dialog, the `NeedsConsent` outcome; UI build clean, 349 UI.Tests pass). **Confirmed 2026-09-01**: on a fresh app build, launching Donkey Kong (#144) auto-installed the catalog pack with no consent prompt and its textures won over the local bootstrap auto pack (log: "auto layer merged: 527 tiles added, 353 overridden by the human layer", tile-match health 98–100%). Found and filed **issue #149** in the process: macOS `open -a Mesen.app <rom>` delivers the file as an Apple "open documents" event, which Mesen does not handle, so no ROM loads — the app must be launched via its bundled binary with the ROM path as argv1 | an accepted `docs/community-packs.json` row matching the loaded ROM auto-downloads on ROM load with no consent prompt, and applies over a bootstrap auto pack |

Edge cases the pipeline must keep handling (evidence from the 2026-08-27
spike, all already covered by `mep_lint.py`): nested zip-in-zip (#64
Zelda), whole-repo archive wrapper (#63, #72, #73), bare root (#62, #67,
#70), named subfolder ≠ ROM (#69), upstream drift creating several
`hires.txt` after acceptance (#63 — fail closed, list candidates), Google
Drive large-file interstitial (out of automatic scope, user supplies).

#### Phase 5 — remaining bootstrap items

Success criterion unchanged: *playing for 5 minutes generates, next to the
ROM, an enhanced game (image level 2, sound level 2/3) with no
configuration; from it an artist reaches a publishable pack in < 1 h
editing only PNG/OGG*. Validation targets: Mega Man 3 (CHR ROM), Contra
(CHR RAM), Link's Awakening (GB), Sonic (SMS).

| Slice | Deliverable | Decision |
|---|---|---|
| F5.4c | shipped 2026-08-29 — `scripts/mep_build.py <folder>`: sheets → tiles → `textures/hires.txt`, new OGGs into `audio/` (`audio/hires.txt`, NES-only — GB/SMS frozen), runs the linter as the gate; `pack` → deterministic zip with generated `pack.json` (MEP-v1 §2.1 rule 6, ADR-0049); `rename-audio-id` id lifecycle (F5.4g item 12). Tile keys come from a key source (`--source`/`textures/hires.txt`/bootstrap `auto/textures/hires.txt`) — not derivable from art. `scripts/test_mep_build.py` in `make doc-checks` | ready |
| F5.4d | shipped 2026-08-29 — "what you played" coverage in the HD Pack Builder window: `HdPackBuilder::GetCoverageReport()` (tiles seen vs with art, screens captured, CHR RAM flag — static export seeds excluded by usage 0, on-disk tiles by their loaded usage) surfaced live via the `GetHdPackCoverageReport` interop into a `Coverage` line + ADR-0043's CHR RAM warning (static export heuristic, "the UI says so"); Before/After preview (`HdPackPreviewWindow`) shows each sheet/screen PNG beside its `*.orig.png` reference twin. `make core` + `dotnet build UI -r osx-arm64` (0/0) green; live recording counts need a GUI run | ready |
| F5.4e | shipped 2026-08-29 — objects from spatial co-occurrence: during screen capture the builder accumulates how often two tile shapes sit 8px apart (E/S neighbors; per-frame bg tile grid filled in `ProcessBgPixel`, accumulated in `OnFrameEnd`), then `BuildObjectSheets` (on save, once) union-finds those edges (≥2 sightings) into objects of 2..32 shapes, writes one editable `textures/sheets/object&lt;NNN&gt;.png` per object (the tiles upscaled and arranged as they appear in-game — BFS from the most-connected shape at its dominant 8px offset), documents the cell order as a `# inferred` comment in `hires.txt`, and emits `# inferred` `tileNearby` condition candidates (inert `<condition>` definitions, deduped by name across sessions) the artist can wire to a `<tile>` after verifying — never auto-attached, so a wrong inference cannot make a tile fail to render. Sprites that co-occur with bg tiles join the same objects; raw OAM-slot grouping is future (the builder sees sprite tiles via `ProcessTile(isSprite)`, not the OAM slots). `make core` + core-unit-tests + doc-checks green; sheet content needs a GUI bootstrap run | ready |
| F5.4g **Block B** | shipped 2026-08-29 — item 3 arpeggio→chord: `DetectArpeggio` (2-4 note cycle at 20-60 Hz from the onset ring) + `FoldArpeggioToChord` folds a fast broken chord into a sustained chord (`MaxChordNotes=4`); item 4 expression: `EvaluateExpression` maps decay/vibrato/portamento onto a pluck×sustained×strings GM patch family (`kFamilyPrograms`), smoothed attacks/releases per slot; item 6 human override: `FixedRole.<ch>` in the ESP (auto/lead/harm/bass) pins the channel via `SetFixedRoles` + per-channel lock in `Decide`/`Update`; ADR-0052 item 2 "channel stolen and returned": `HandleChannelSteal` hands a channel's native role back on resume, bypassing the swap hysteresis. `make core` (full clean rebuild — the header-size change makes incremental builds SIGSEGV), core-unit-tests 109/109, `roles-probe` regression on Zelda + Mega Man 3 (stable roles, SFX segments detected), `make doc-checks` green. GUI/listening validation of the rendered audio is recorded as pending | ADR-0052 |
| F5.4g **Block C** | 8 loop point in the fingerprint (`LoopPosition` is 0 today), 9 SFX audible during OGG (mute mask), 10 music→music transition/fade | **done 2026-08-29.** item 8 (ADR-0134 Option A: `tracks[i].loop`, MEP-v1 §5.2, renderer emits from a MIDI loop marker, lint accepts presence/absence, Bloco H round-trip — 121/121, commit 4a9c096c); item 9 (ADR-0133: `SetReplacementMuteMask`, classifier-driven SFX pass-through, bool shim removed, fallback 0x0F, reset clears — commit c9b7353c); item 10 (**ADR-0142 accepted 2026-08-29**: 40 ms crossfade on BGM switch/stop, run-ahead-gated — commit c36043f5). Pending (listening, manual): loop-intro não repete, SMB1/Zelda SFX audível, switch sem clique |
| F5.4g **Block D** | 11 *Extract audio* opt-in tool driving the sound driver — **tool shipped 2026-08-29**: `scripts/spike_sound_driver` productised with the full ADR-0135 contract (per-id **frame** budget + whole-run wall-clock budget, SIGINT abort at frame boundaries, guaranteed no-op → `enumeration.log` only, F5.3 fingerprints + midi relocated into `<sibling>/auto/audio/`). Runs as its own process (ADR-0135 decision-5 alternative; recorder flushes only at teardown → ABI `Release()` before relocation). Validated headless: no-op (budget 20s → exit 4, log-only, no fingerprints) and success (Zelda mailbox $0600 validates → fingerprints.json + 2 bgm midi + enumeration.log). **GUI wiring shipped 2026-08-29 (ADR-0135 point 7)**: new `Utilities/ProcessUtilities.{h,cpp}` (detached `fork`/`execvp` + `GetExecutableFolder` — the checklist's process-spawn utility, standalone-tested PASS), `EmulatorShortcut::ExtractAudioHdPack` (SettingTypes.h + C# mirror), `NesConsole` case + `ExtractAudioHdPack()` handler (NES-only, GB/SMS ignore explicitly), tool resolver (`MESEN_EXTRACT_AUDIO_TOOL` env → app-exe dir → `<Mesen home>/Tools`, the app data folder), `HdPackBuilderViewModel.ExtractAudio()` gated on NES + button + localisation. `make core` (full clean rebuild — shared header) green, `dotnet build UI` 0/0, end-to-end headless spike PASS (synthetic ROM → shortcut → resolver → detached child with the pack folder forwarded). GUI button-click on a real display pending (manual)** — **run 2026-09-01**: HD Pack Builder's Extract Audio button on a real display started the detached probe (`spike_sound_driver` placed under `<Mesen home>/Tools`, the resolver's actual second path, not `$HOME` — fixed a stale comment/log-message that said `~/Tools`), which ran to its 300s wall-clock cap and exited via the documented no-op path (no validated mailbox trigger found, only `enumeration.log` written, no fingerprints/midi) — the success path was already covered by the headless spike, this pass confirms the no-op path end-to-end through the GUI**; 12 id naming/cleanup — `rename-audio-id` (F5.4c) + `scripts/audio_cleanup_suggest.py` **shipped 2026-08-29** (report-only pruner reading `enumeration.log`: flags short/title/repeat/silent ids, notes the id↔trackNN not-1:1 mapping, tested in `test_mep_build.py`); 13 `mep_build.py` `audio/` + audio lint (F5.4c) and seed-MIDI→OGG tutorial **shipped 2026-08-29** (`docs/hd-pack-authoring.md` §"Seeding audio", record→render→promote→build) | **ADR-0135** (accepted 2026-08-29, implemented-variant note) and **ADR-0051** (accepted 2026-08-29) |
| F5.4b follow-ups | (a) saturation log when a shape hits `MaxPaletteVariantsPerTile`; (b) seed `_paletteVariantsByShape` from `_hdData` or document per-session scope | ADR-0132 — shipped 2026-08-29: (a) logs once per shape (`_variantCapLogged`); (b) seeds from non-defaultTile on-disk entries in the ctor, making the cap a per-shape total across sessions |
| SoundFont | decided 2026-08-29 — **bundle GeneralUser GS (31 MB, permissive) in the installer**; level-2 GM works out-of-the-box, `.sf2`-hunting no longer required | done — bundle on the release path (blocked by the installer itself, which has no release yet) |
| F5.5 | wrap-up — shipped 2026-08-29: (a) **bootstrap setting UI polish** — localized the last hardcoded pack-UI strings (EnhancementPacksWindow auto-install + P.3 preferred-pack labels, MainWindow Player overlay + pack picker, the P.5 "Applied" toast; on-screen messages moved to the Core `MessageManager::_enResources` map where the HUD actually localizes — the UI `resources.en.xml` is the window-label system); (b) **MEP-v1/MEI golden refresh** — goldens verified current and the 5 golden/recipe/validate-specs gates wired into `make doc-checks` (33 checks); (c) **README** — Player mode (P.4–P.6), Extract Audio tooling, community flow; (d) **F1–F3 regressions** green (MIDI/VGM on Mega Man 3, HD-pack skeleton on Zelda, MEP host path clean, core-unit-tests exit 0); (e) **dotnet 0 warnings** (build UI 0/0) | — |

#### Repo hygiene and tests

| Slice | Deliverable | ADR |
|---|---|---|
| H1 | `make doc-checks` running `verify-fase0-1-dox.sh`, `verify-ui-logic-firewall.sh` and `check-file-loc.sh` per guarded file; CI runs it before builds; `scripts/AGENTS.md` names the target | **0137** (accepted; file deleted — see D1) |
| H2 | `.github/AGENTS.md` records the `unit-tests.yml` contract invariants (clang only, …) | **0131** (accepted; file deleted — see D1) |
| H3 | `path-cases.txt` fixture header format / control characters | **0124** (accepted) |
| H4 | `mep_compare.py`: per-system dispatch of `render_original` + NES golden texture pack | **0136** (accepted; file deleted — see D1) |
| H5 | UI-logic host-free firewall parity scan in CI | **0123** (accepted) |
| H6 | UI-logic public helpers for direct testing | **0125** (accepted, Option A) |
| H7 | `CheatTypeDetector` ThrowsAny (GB/SMS product decision still deferred) | **0128** (accepted) |

#### Documentation and normative integrity (audit 2026-09-01)

Source: a documentation audit run on 2026-09-01 and re-verified against
the tree, `git log` and the GitHub issues the same day. Verdict: the
shipped record above matches the code (every "shipped" ADR resolves to
code, every cited script/workflow/golden exists, `make doc-checks` exits
0). The defects are normative gaps — specs that never received a
promised field, ADR files deleted by an unrelated commit, product
decisions recorded only in issue comments — plus stale prose. Slices
are ordered by priority; D1–D4 gate any further ADR-driven work because
each later slice would otherwise inherit the same broken references.

Not defects (checked and dismissed): the run ids quoted in ADRs
(`45092f2ebec4` etc.) are `.dev-squad/runs/` directories, unversioned by
design, not squashed commits; the `unit-tests.yml` contract itself is
not lost — it lives in `.github/AGENTS.md` lines 260–283 with a
self-check, only its ADR record (0131) is gone; ADR-0141's header already
declares "amends ADR-0138 §37" and ADR-0147 already declares
"Supersedes / amends" ADR-0049/0050 — the missing half is the back-pointer
in the amended file.

| Slice | Deliverable | Priority | Evidence |
|---|---|---|---|
| D1 | Restore `.dev-squad/adr/0130`, `0131`, `0136`, `0137` from `b0b334b0^` (an F6.2b fix commit deleted them on 2026-08-28; 0132–0135 were restored the same week, these four were not). Keep them `accepted` (H1/H2/H4 shipped) or mark `superseded` with a "Superseded by" line; never re-mint the ids (ADR-0035) | **P0** — **shipped 2026-09-01** (restored with Status notes; `scripts/checks/verify_adr_refs.py` wired into `make doc-checks`) | still cited by ADR-0122/0126/0129, by H1/H2/H4 above, by `.github/AGENTS.md` (4×) and `docs/specs/golden/mep/audio/README.md` |
| D2 | MEP-v1 **v1.4**: `id` as SHOULD in §3.1 (ADR-0140 source 1, Part B §3.3 rule 1); golden `pack.json` in `golden/mep/` and `golden/mep-nes/` gain `id`; `mep_lint` validates the slug shape | **P0** — **shipped 2026-09-01** (`mep_lint` reports a malformed/missing `id` as a warning, never an error — the spec says hosts never fail a load on it) | MEP-v1 is still v1.3 with no `id`; the catalog already emits `pack_id`, so the field's only normative home is an ADR |
| D3 | MEI-v1 **v1.2**: define `rom.sha1s` (alternate No-Intro hashes of the same game) — or drop it from the generator | **P0** — **shipped 2026-09-01** (`rom.sha1s` §2.4 + `validate-specs.py` checks; `mei_catalog_entry.MEI_VERSION` = 1.2.0 and `docs/community-packs.json` declares it) | emitted by `generate_community_pack_catalog.py:118`, present in 6 of 11 rows of `docs/community-packs.json`, absent from MEI-v1 (which knows `sha1` MAY + `crc32`) |
| D4 | ADR recording the 2026-08-31 catalog removal of audio-only NEA packs: the rule (a listed pack must be self-contained and texture-bearing; a stale shared-zip sha256 is grounds for removal, not silent failure), how it squares with the auto-load-every-accepted-pack policy (CLAUDE.md, ADR-0146) and with ADR-0143's N-slot expansion, and what re-listing requires | **P0** — **shipped 2026-09-01** (ADR-0148, amends ADR-0144: the bundled patch must also be wired; `mep_lint` labels each bundled patch wired/NOT wired and `.github/ai/validate-classify.md` applies the audio exception only to a wired one and refuses non-listable packs under rule 1) | #128–#131, #133–#136 are `pack:valid` + `pack:split` yet closed; rationale exists only in the closing comments and commits `fd244f2a`/`7bc8f13a` |
| D5 | In-place amendments: ADR-0138 header ("F6.2–F6.5 remaining" → F6.0–F6.7 shipped), §37 note pointing to ADR-0141's `content_id` trigger, §38/§51/§54 consent clauses marked superseded by ADR-0146, F6.4c marked shipped (fixtures in `docs/specs/golden/mep-recipe/fixture/`); ADR-0143 header gains "Amends ADR-0140 source 2"; ADR-0049 gains a pointer to ADR-0147 | P1 — **shipped 2026-09-01** (ADR-0138 header/§37/§38/§51/§54/F6.4c annotated in place; ADR-0049 points to ADR-0147) | current text of ADR-0138 line 581 still says reinstall on `source.sha256` |
| D6 | F6.7 cleanup — remove the inert consent plumbing (`CommunityPackAutoInstallConsentGiven`, `CommunityPackConsentState`, the `NeedsConsent` outcome and its dialog), as ADR-0146 Consequences require | P1 — **shipped 2026-09-01** (`CommunityPackConsentState.cs` + its test deleted, flag/dialog/`NeedsConsent` removed, `EvaluateGates` reads `AutoInstallCommunityPacks` directly; UI build 0 errors, 349 tests pass) | same item as the F6.7 "Remaining" cell above |
| D7 | Fill `## Consequences` / `## Alternatives` of ADR-0139–0145 (all seven are empty) with the verified implementation state and the options rejected | P1 — **shipped 2026-09-01** (Consequences/Alternatives filled for 0139–0145 with file:line state; ADR-0143 header now "Amends ADR-0140 source (2)") | code × doc cross-check is impossible for them today |
| D8 | ADR-0120 §3 (optional ROM-name parameter in the C# `MepZipValidator`) and §4 (standalone C++ E2E zip-pipeline harness): implement, or record an explicit deferral with a date | P1 — **deferred 2026-09-01** (both recorded in place in ADR-0120: §3 has no caller with a ROM in scope and the Python mirror normalizes names; §4 is covered by `verify_community_install_from_zero.py` except the zip path — pick up with a per-ROM install caller) | both are "named follow-up, not this task" since 2026-08-27 |
| D9 | Stale docs: `docs/hd-pack-authoring.md` (binary verdict, real labels — `pack:mep-full`/`pack:partial-hd` never existed); `docs/community-pack-intake-handoff.md` ("already cataloged" rows SMB #135, SMB2 #134, 1942 #128, Duck Hunt #131 are closed, not listed); `docs/enhancement-ecosystem.md` (cites `Core/SNES/Coprocessors/MSU1` — `Core/SNES`, `Core/PCE`, `Core/WS` are empty skeletons — replace with a pointer to this PRD); `MIGRATION.md` (issue #4 → #137, "exporter not built" superseded by ADR-0147, binary verdict); `docs/specs/README.md` (index `golden/mep-content-id.json` and `golden/mep-nes/`) | P2 — **shipped 2026-09-01** (7 closed NEA issues moved to a "De-listed" table citing ADR-0148; golden index added) | each asserts a fact that is false today |
| D10 | `CLAUDE.md`: resolve the Author contradiction (one paragraph says the form field was removed and the classify step discovers authorship, another says "Author" is the declared form field; in practice the classify step never writes `author`, so every catalog row lacks one — decide: classify writes `author` or the sentence goes); list the current labels (`pack:split`, `pack:needs-review`, `assets:external` are missing); the `deps` sentence vs 0 of 11 rows using it | P2 — **shipped 2026-09-01** (Author = classify → mep-meta → catalog, 1/11 rows named; 14 real labels listed; `deps` "when present", 0/11 rows; follow-up: stale docstring `scripts/community_pack_markdown.py:73-76`) | `generate_community_pack_catalog.py:69` reads `author` from mep-meta only |
| D11 | Replace line citations with target names: `makefile:233` in ADR-0126/0129 (target `core-unit-tests` is at `:302`), `makefile:254` in ADR-0135 (`spike-sound-driver` is at `:335`) | P2 — **shipped 2026-09-01** (target names in ADR-0126/0129/0135; ADR-0131/0137 converted 2026-09-01 as well; `grep makefile:[0-9] .dev-squad/adr` is empty) | lines drift on every makefile edit |
| D12 | Hygiene: version `scripts/build_app_macos.sh` (local `.app` build — dylib injection + ad-hoc codesign — that CI does not do; untracked today); annotate ADR-0035 that ids 0139–0147 were reissued twice (ADR-0138 lines 238/348) and are now bound to the live ADRs; decide whether the empty `Core/SNES`, `Core/PCE`, `Core/WS` directories stay | P3 — **partly shipped 2026-09-01** (`build_app_macos.sh` header + `scripts/AGENTS.md` bullet; ADR-0035 records the three id re-mints). `Core/SNES`, `Core/PCE`, `Core/WS` (empty, untracked, unreferenced) deleted 2026-09-01 | — |
| D13 | MEI-v1 **v1.3**: document the additive per-pack fields the generator already emits — `pack_id` (ADR-0140/0143), `content_id` (ADR-0139), `votes` (ADR-0140, non-normative; PRD Part B §5 sort key) — with golden `mei/manifest.json` and `validate-specs.py` checks; also make the classify step refuse non-listable packs (ADR-0148 rule 1 — prompt text landed 2026-09-01, needs one CI run to confirm) | **P1** — **shipped 2026-09-01** (`pack_id`/`content_id`/`votes` §2.5 + golden `mei/manifest.json` + `validate-specs.py` per-entry shape checks via `mei_rules.mei_identity_field_errors`; `mei_catalog_entry.MEI_VERSION` = 1.3.0 and `docs/community-packs.json` declares it; the ADR-0148 rule-1 classify refusal is NOT yet confirmed — still needs one CI run) | found by D7: `docs/specs/MEI-v1.md` has 0 hits for `pack_id`/`content_id`/`votes` while all 11 rows of `docs/community-packs.json` carry them |
#### Host input tester (host UX, not a pack feature)

Goal: Settings → Input → **Test** tab that shows, with no ROM loaded, every
connected pad (name, backend, `PadN` slot), live buttons/axes with the same
keycode names used in mapping, the deadzone ring and drift warning, and a
rumble test; the mapping window highlights the console button being
pressed. Layer 1 (host) + layer 2 (binarised keycode), side by side; the
in-game `InputHud` stays the layer-3 source of truth.

| Slice | Deliverable |
|---|---|
| I.0 | shipped 2026-08-29 — `GamepadInfo`/`GamepadState`/`GamepadBackend` on `IKeyManager` (`GetConnectedGamepadCount`/`GetGamepadInfo`/`GetGamepadState`/`TestForceFeedback`, defaulted no-ops) + Windows (`XInputManager::IsConnected`/per-port FFB, `DirectInputManager::GetName/VendorId/ProductId`), Linux (`LinuxGameController` name/VID/PID/rumble via libevdev) and macOS (`MacOSGameController::GetName`/`HasRumble`) impls; `InputApiWrapper.cpp` C-ABI exports + `InputApi.cs`. `GetPressedKeys` untouched (Lua/`GetKeyWindow`/shortcuts keep working; new exports only). `make core` + `gamepad_probe` smoke (clean, count=0 without a pad) + UI build green; Windows/Linux are source-only on this macOS build |
| I.1 | shipped 2026-08-29 — `GamepadTesterViewModel` (+`GamepadTestItem`, `GamepadButtonState`): the Test tab (Settings → Input) lists every connected pad (name, backend, `PadN` slot, VID:PID, rumble) with live 24-button indicators and raw int16 axes, fed by `Refresh()` from a ~16ms `DispatcherTimer` that only runs while the tab is selected (`IsTestTabVisible`); the constructor never calls `InputApi`; kept in `UI/ViewModels/` (not `UI/Logic/`). Rumble test button (300ms pulse). **Deadzone ring + drift warning shipped 2026-08-29**: the left stick shows a ring (outer = full travel, inner red = the config deadzone at the DirectInput-canonical extent), a live green dot, magnitude %, and a drift warning when the stick rests past the deadzone for ~500ms — via host-free `UI/Logic/GamepadStickDiagnostics` (`DeadzoneRatio` mirrors Core's `EmuSettings` mapping) + `GamepadDriftDetector` (sample-count based, deterministic). UI build 0/0, doc-checks green. GUI run pending (no pad on this machine) |
| I.2 | shipped 2026-08-29 — `KeyBindingButton.Highlighted` (class `highlighted` → theme style) + a ~16ms timer in `ControllerConfigWindow` that highlights every `KeyBindingButton` whose binding matches a currently-pressed key (via `InputApi.GetPressedKeys`), re-collecting buttons on tab switch; stopped on close. UI build green; live highlight needs a GUI run to verify |
| I.3 | **circularity test shipped 2026-08-29** — `UI/Logic/GamepadCircularity` (host-free): buckets samples by angle into 16 sectors, score = coverage² × radial consistency (1.0 = full, uniform reach); "Excellent/Good/Fair/Poor" ≥ 0.85/0.7/0.5, hint until ≥ 48 samples (~0.8s rotation); VM accumulates the left stick (Reset button), `GamepadDiagnosticsTests` 14 cases (circle/line/square-gate/dead-quadrant/insufficient/deadzone/drift/ratio). **Per-device deadzone shipped 2026-08-29** — `UI/Logic/PerDeviceDeadzone` (host-free): a pad keyed by VID:PID uses its own override when one exists, else the global setting, sizes clamped 0-4; `InputConfig.PerDeviceDeadzones` (host-only — not mirrored to the core, whose input path stays global-only); the Test tab shows a 0-4 toggle per pad with a "per-device"/"using global setting" label + reset, persisted via the existing config apply lifecycle. `PerDeviceDeadzoneTests` 11 cases; 258/258 + UI build 0/0 + doc-checks green; visual ring check still needs a pad. **binding by VID/PID** — resolved at the tester's scope: a setting bound to a pad's physical identity is exactly the per-device deadzone above (keyed by VID:PID); a full per-device *keymap* binding is a separate product decision and is out of this tester's scope (adjacent to the OUT'd automatic remapping). Remaining (hardware-gated): MBC7/GBA tilt UI, Linux `UpdateDevices()`, macOS pads without `extendedGamepad` |

Out: preset redesign, HUD overlay, special devices (Zapper, Power Pad,
Phaser), automatic remapping, browser Gamepad API, stats collection.

#### Deferred / optional

- OGG replacement audio on GB/SMS (`hires-gbsms-v1-draft`) — frozen until a
  second implementer exists (ADR-0041).
- ML-model upscale as an alternative to xBRZ in `scripts/` — later.
- Automatic IPS relocation across ROM revisions — no.
- Offline AI tools (ESRGAN batch upscale, LLM-assisted preset tuning) —
  optional external tools on top of the bootstrap, never in the emulator.
- Pack browser UI beyond auto-install (search, ranking by GitHub signals,
  user-configurable extra MEI URLs with explicit confirmation, MEI §3.4) —
  after Phase 6, if the catalog grows past what a list can show. The
  player-shell picker (one ROM, 2+ `pack_id`s) is **not** that browser;
  it lives in Part B §5.

#### Phase 7 — Player shell (minimal GUI)

Default chrome is a player shell (recent games, drop a ROM, packs apply
themselves, thin overlay) with **Advanced GUI** restoring classic Mesen.
Pack identity is the pair `pack_id` (product, stable across versions) +
`content_id` (revision, hash of the resolved tree after unzip) — the
source-zip sha256 is the download, not the pack. The catalog keeps **one
live slot per `pack_id`**; the player never picks among versions.

Normative text, slices P.0–P.7, and open ADR topics: see Part B
below. Do not duplicate that prose here.

Depends on: F6.4b for catalog auto-install in the overlay (P.6). P.3–P.5
can run on local packs before F6.4b. P.0 ADRs must be accepted before
P.1/P.2.

Status: **Phase 7 fully shipped — P.0–P.6 done (2026-08-29).** P.4 shipped
the `UiMode` default rule, the Player overlay + its Esc-owned shortcut,
hidden menu, recent-games home and the Advanced switch; P.5 shipped the
Player pack picker decision and panel (2+ competing pack_ids, sibling
suppresses, pick power-cycles, dismiss asks again), the current-pack chip
and the apply toast; P.6 wired the overlay to the F6.4b catalog
install/update through the §3.6 `content_id` trigger (wrapper-only no
reinstall, no auto-downgrade, removed slot keeps the install) and made
community 👍 sort the picker — see the Part B header.

#### Phase 8 — Enhancement pack border layer

A pack-declared decorative frame/border rendered around the game area
(the one enhancement-toggle idea from the Player overlay's quick-toggle
panel — see Part B §6.1 — that isn't UI over an existing
setting). Needs: (1) a new optional field in the MEP-v1 manifest for a
pack to declare a border asset; (2) a new Core compositing path that
draws it around the emulated frame; (3)
`EnhancementPackConfig.EnableBorder` gating it, consumed by the P.7
toggle. This is Core/pack-format work, not chrome, so it stays in Part A
(pack/core), not Part B (chrome) — see `docs/roadmap/AGENTS.md`'s
ownership split.

Non-goals: retrofitting existing HD packs with borders automatically;
per-console border art (a border is a pack asset, not an engine feature).

| Slice | Deliverable | ADR |
|---|---|---|
| F8.1 | ADR: MEP-v1 border field shape + Core render/compositing approach | **not written yet — blocks this phase** |
| F8.2 | `EnhancementPackConfig.EnableBorder` + Core render path + `mep_lint` validation, once F8.1 is accepted | F8.1 |

Status: **proposed (2026-08-30)** — not started; F8.1 (ADR) is the
critical path.

### 5. Order of execution

1. ~~F6.2 → F6.3 → F6.3b → F6.4a → F6.4b → F6.4c → F6.5 → F6.6~~ shipped 2026-08-28/29; F6.7 core shipped 2026-09-01, cleanup pending (= D6).
   - **D1 → D2 → D3 → D4** (documentation integrity, P0) before the next
     ADR-driven slice; D5–D12 opportunistically, one run or one manual
     pass each.
2. ~~H1–H4~~ shipped (2026-08-27/28).
3. ~~Phase 5 Blocks B–D, F5.4c/d~~ shipped 2026-08-29 (ADR-0133/0134/0135
   accepted; SoundFont decided: bundle GeneralUser GS). Remaining Phase 5
   items are the manual checks named in each row.
4. **Input tester I.0–I.2** independent of everything above.
5. **Phase 7 (player shell)** — P.0 ADRs, then P.1–P.5 independently of
   F6.4b; P.6 after F6.4b. See Part B.
   P.7 (quick-toggle panel + welcome/Continue cards) is independent of
   Phase 8 below — it ships without a Border toggle and adds one later.
6. **Phase 8 (border layer)** — F8.1 (ADR) first, F8.2 after acceptance.

### 6. ADR map

| ADR | Status | Meaning for this roadmap |
|---|---|---|
| 0138 | accepted | Phase 6 design; F6.0–F6.7 shipped (headless; F6.6 includes the empty-section-path round-trip fix — §3.2; F6.7 core 2026-09-01); remaining: F6.5 GUI end-to-end install acceptance (user-supplied audio, manual), F6.7 consent cleanup (D6). Its own text is stale — header still says "F6.2–F6.5 remaining", §37 still names the `source.sha256` trigger (amended by ADR-0141), §38/§51/§54 still require consent (superseded by ADR-0146): in-place amendment is slice D5 |
| 0137, 0131, 0124, 0136 | accepted 2026-08-27; all shipped 2026-08-28 | H1–H4. ⚠ The files of 0130/0131/0136/0137 were deleted by commit `b0b334b0` (2026-08-28, an unrelated F6.2b fix) and never restored — only 0124 exists on disk; restore from `b0b334b0^` (slice D1). Their substance survives: the CI contract in `.github/AGENTS.md`, the hygiene checks in `make doc-checks` |
| 0143 | accepted 2026-08-29 | one catalog slot per **game**: `pack_id` = origin × game (`owner/repo:<game-slug>`), multi-game zips expand into `pack:split` sibling issues; amends ADR-0140 source 2 (header note pending, D5) — Part B §3.3 |
| 0144 | accepted 2026-08-29 | audio packs may ship their `.ogg` tracks via a bundled ROM patch + install-time extraction |
| 0145 | accepted 2026-08-31 | optimistic matching on SHA1 mismatch: textures + BPS auto-apply, IPS/audio/synth stay gated; tile match-rate health monitor auto-disables a wrong optimistic pack |
| 0146 | accepted 2026-09-01 | auto-load every accepted pack: no first-run consent gate; `AutoInstallCommunityPacks` is the single switch; supersedes the consent clauses of ADR-0138 §38/§51/§54 (F6.7) |
| ADR-0148 — de-list audio-only NEA packs; a catalog row must be a self-contained, verifiable artifact | accepted (2026-09-01) | records the 2026-08-31 removal; amends ADR-0144 (bundled patch must be wired, not merely present) — slice D4 |
| 0121 | accepted 2026-08-27 (option A, shipped `805cb10d`; §2.1 rule 9 wording shipped with F6.1) | legacy bare `hires.txt` fallback is the norm |
| 0132 | accepted | F5.4b follow-ups (a)/(b) |
| 0133, 0134, 0135, 0051 | accepted 2026-08-29 (0134 = Option A: `loop` field in `fingerprints.json`) | unblocked Blocks C/D; Block C shipped 2026-08-29 (items 8/9/10) |
| 0142 | accepted 2026-08-29 | Block C item 10 crossfade contract — implemented in c36043f5; click-free listening verification manual-pending |
| 0123, 0125, 0128 | accepted 2026-08-29 | H5 UI-logic firewall parity scan (all five checklist items); H6 public test-facing helpers (Option A); H7 CheatTypeDetector ThrowsAny (GB/SMS product decision still deferred) |
| 0040/0044/0047/0049/0050/0052/0120 | accepted | shipped foundations; do not diverge without amending |
| 0147 | accepted (2026-09-01) | sibling pack folders `auto/` (recorder) + `mep/` (edited MEP pack); catalog install materializes to `<sibling>/mep` with a central fallback (amends ADR-0138 §4); hd-legacy packs are MEP-ized on install; Restore action (baseline registry); update never silently clobbers a local edit (baseline `content_id`) |
| player-shell identity + chrome | ADR-0139/0140/0141 accepted (2026-08-28) | `content_id` algorithm, `pack_id` sources (incl. `local:` fallback), amendment to ADR-0138 §37 (update trigger = `content_id`), `UiMode`; listed in Part B §9; `UiMode` still without an ADR |

### 7. Risks

| Risk | Mitigation |
|---|---|
| Project framed as a distributor of derivative content | catalog holds URLs + hashes + licences only; client never scrapes third-party hosts; user supplies unlicensed audio |
| Recipe vocabulary grows into a scripting language | new op = new `recipe` major + new ADR; clients skip unknown versions |
| Two agents implementing the same ADR in parallel | one dev-squad run per slice; the autonomous squad daemon (`.claude/scheduled_tasks.lock`) must be stopped while another agent works on an `accepted` ADR |
| Upstream pack drift after acceptance | sha256 in the catalog + drift check; client reinstalls when the slot's `content_id` changes (ADR-0141) — a wrapper-only sha256 change does not reinstall |
| Catalog-shaping decisions recorded only in issue comments or commit messages (the 2026-08-31 audio-only NEA removal) | every such decision gets an ADR or a PRD line the same day; D4 backfills the one already made |
| ADR files deleted by an unrelated commit go unnoticed (0130/0131/0136/0137, 2026-08-28) | D1 restores them; `make doc-checks` should fail on a dangling `ADR-NNNN` reference (add to D1's acceptance) |
| Scope explosion | phases independent; GitHub is the only backend; no telemetry |

### 8. References

- SUPER ZSNES — https://www.zsnes.com/ · VGMusic · romhack.ing · Zeldix (MSU-1, other hosts)
- No-Intro DATs — https://no-intro.org/ · rcheevos `rhash` · vgmrips (VGM/GD3) · beat/BPS spec
- Precedents: *MGM v. Grokster* (2005); Yuzu/Nintendo settlement (2024)

---

## Part B — Player shell (default GUI)

**Status:** active (2026-08-28) — product text of §3–§6 accepted by the
user on 2026-08-28; P.0 done (ADR-0139/0140/0141 accepted 2026-08-28);
P.1 done (content_id in scripts/ + Core, mep-meta + `.mep-install.json`,
golden parity — 2026-08-29); P.2 done (catalog/mep-meta/MEI identity +
one slot per pack_id — 2026-08-29); P.3 done (per-ROM preference resolver
+ Advanced picker — 2026-08-29); P.4 done (`UiMode` default rule + Player
chrome + overlay + Esc precedence in the shortcut config — 2026-08-29;
GUI acceptance pending a manual pass on a real display); P.5 done (Player
pack UX: picker decision + panel, current-pack chip, apply toast —
2026-08-29; picker/dismiss/sibling manual pass pending); P.6 done (§3.6
catalog update trigger wired into F6.4b, wrapper-only no-reinstall,
no-auto-downgrade, removed slot keeps install, votes sort the picker —
2026-08-29). **Phase 7 fully shipped (P.0–P.7)** — P.7 done 2026-09-01
(Enhancements quick-toggle panel + welcome/Continue cards, §6.1–§6.2; GUI
pass pending) ·
**Author:** sbihaiko ·
**Scope:** MesenCE fork (`main`); nothing goes upstream ·
**Parent roadmap:** Part A of this document (Phase 7 entry). Pack/core
work stays there (Phase 6 F6.4b/c/F6.5, Phase 5,
input tester). This Part (Part B) owns chrome, pack identity,
duplicates, and
the player-facing choice between packs ·
**Specs:** [MEP-v1](../specs/MEP-v1.md) · [MEI-v1](../specs/MEI-v1.md) ·
[MEP-recipe-v1](../specs/MEP-recipe-v1.md) ·
**Decisions:** identity model (§3) and one-slot rule (§3.6) are accepted
product requirements, specified by ADR-0139 (`content_id`), ADR-0140
(`pack_id`, catalog uniqueness) and ADR-0141 (one slot, client update
trigger — amends ADR-0138 §37). Chrome (§6) is a product requirement; it
needs an ADR only if P.4 finds trade-offs beyond what §6 states ·
**Process:** one dev-squad run per **slice** (P.1, P.2, …). Settle the
slice's ADRs first. A slice is done when its acceptance checks pass and
this header plus Part A's Phase 7 entry are updated.

---

### 1. Vision

The fork's thesis is *faithful, then enhanced, on by default*. The current
GUI is still classic Mesen: File / Game / Options / Tools / Debug / Help,
plus debugger, HD Pack Builder, netplay, movies, Lua. That chrome is
correct for authors and for anyone who already lives in Mesen. It is the
wrong first screen for a player who should drop a ROM and already hear and
see the enhanced game.

Default chrome becomes a **player shell**: recent games, drop a ROM, the
game fills the window, packs apply themselves, a thin overlay for pause /
save / pack / settings. **Advanced GUI** restores the classic Mesen menus
and tools unchanged.

This is one Avalonia process and one window, not a second binary. Player
and Advanced are chrome modes over the same ViewModels.

The legal principles of Part A §1 still apply: the official
channel carries URLs + hashes + licences, never third-party assets; hosts
never execute pack content as code; no LLM in the client.

Product consoles stay NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA
(`docs/roadmap/AGENTS.md`). SNES gamepads stay as input.

### 2. Problem

Three pack-identity problems and one chrome problem.

**Identity**

1. **The zip the catalog hashes is not the pack.** Community submissions
   are GitHub `/archive/` trees, release zips, nested folders, whole
   repos. After ADR-0120/0121 discovery (and a MEP Recipe, when there is
   one) the host loads a *subset* of that zip. Two wrappers of the same
   tree look like two packs if identity is the source sha256. One primary
   zip plus two different recipes is two packs even when the source
   sha256 matches. Today's "Pack Hash" (mep-meta `source_sha256`, MEI
   `sha256`) is the download, not the pack.
2. **A content hash alone cannot version a pack.** Contra80s 1.0 and 1.2
   are the same product and two artifacts. If the unique id is the
   resolved-tree hash, they look like two competing packs for the same
   ROM and the player is asked to choose. Updates need a stable lineage
   id; integrity and duplicate-bytes detection need the content hash.
3. **Several real packs can target the same ROM.** That is not a
   duplicate. The player has to pick one, and the choice has to stick
   per ROM. Today the host applies the first lexicographic container
   (ADR-0040) and hides the rest behind Tools → Enhancement Packs (MEP)….

**Chrome**

4. **The GUI fights the product.** Enhanced Audio is already on by
   default (`AudioConfig.EnableEnhancedAudio = true`); bootstrap already
   writes `<Game>/auto/` beside the ROM; F6.4b will auto-install from the
   catalog. None of that reads as a player product while Debug and HD
   Pack Builder sit in the menu bar.

### 3. Pack identity — two ids, not one

A pack is a *product* that has *revisions*. Treating the content hash as
"the" unique id makes versions look like different packs. Treating the
source-zip sha256 as "the" unique id makes wrappers look like different
packs. Neither is sufficient alone.

#### 3.1 Four names, four jobs

| Name | What it identifies | Changes when | Already exists? |
|---|---|---|---|
| **`pack_id`** | the product (lineage). "This is Contra80s by Tastic." Shared by every revision | never, unless it is a different product | no — new (§3.3) |
| **`content_id`** | one revision: the canonical resolved pack tree the host will load | any loaded file changes | no — new (§3.2) |
| **`version`** | human/semver label of that revision | the author bumps it (can lie; `content_id` is the truth) | yes — `pack.json` `version` (MEP-v1 §3.1, MUST); absent on `hd-legacy` |
| **`source_sha256`** | the downloaded bytes (the wrapper) | the zip wrapper changes, even if the inner tree does not | yes — board "Pack Hash", mep-meta `source_sha256`, MEI `sha256`, `.mep-install.json` `source.sha256` |

Also **not** a pack id:

- **ROM No-Intro sha1** — the game. Many packs share one; one pack may
  list several `targets[]`.
- **GitHub issue number** — the submission. A second issue can be the
  same `pack_id` (duplicate submit) or a different one (competing pack).
  Useful as catalog provenance (`issue`, already in MEI v1.1 §2.2), not
  as the product id.
- **Container file name** — the local discovery key (ADR-0040/0049). It
  is the fallback `pack_id` for a folder the user dropped (§3.3), never a
  catalog id.

#### 3.2 `content_id` — identity of a revision

Computed **on the tree the host would actually load**, not on the zip
bytes: discovery first (MEP-v1 §2.1 rules 5–9, ADR-0120/0121), then the
recipe when one exists.

- **No recipe:** unzip → find the pack root → hash that tree. A GitHub
  archive whose pack lives in `HdPacks/Contra (U) [!]/` hashes only that
  subfolder. `__MACOSX/`, `.DS_Store`, README, screenshots outside the
  root do not enter the id.
- **With a recipe:** `content_id` is a function of (hash of the resolved
  *primary* tree, `recipe_hash`, the declared dep sha256s). CI can compute
  it without fetching `user_supplied` deps (it has the primary zip and the
  recipe's declared digests). Two recipes on the same primary zip are two
  revisions. The same recipe plus the same deps is the same revision even
  if CI never saw the dep bytes. The client computes the same function
  **at install time**, when `MepRecipeInstaller` still holds the primary
  bytes, and stores the result in `.mep-install.json` (§4); it does not
  re-derive it from the installed output tree.

Exact canonicalisation (path order, which files, newline folding, zip
entry metadata ignored, whether `pack.json` `version` is part of the
payload) is the P.0 ADR. The product constraint is: **same loaded files
⇒ same `content_id`; wrapper-only change ⇒ same `content_id`; any
loaded-file change ⇒ new `content_id`.** Recommendation for the ADR:
hash payload files, not the `version` string, so a label-only bump is not
a new revision.

`content_id` answers: *are these two artifacts the same bytes the
emulator will play?* It does **not** answer: *is this Contra80s 1.2 or a
different Contra pack?*

The algorithm has **two implementations, one normative reference**, like
the recipe interpreter (ADR-0138 §39): `scripts/` (CI, normative) and the
Core (client). A parity fixture keeps them equal.

#### 3.3 `pack_id` — identity of the product

Stable across revisions. Source, first match wins:

1. An explicit `id` field in `pack.json` (slug, lowercase, unique in the
   official catalog). This is a MEP minor bump and part of the P.0 ADR.
   Best long-term id; authors already have `name`/`version`/`author`.
2. Else, for a `github.com` / `codeload.github.com` pack URL:
   `owner/repo` (the origin, not the tag or release filename).
   `/archive/v1.2.zip` and `/releases/download/v1.2/pack.zip` of the same
   repo are the same product.
   **Amended by ADR-0143 (2026-08-29):** the `pack_id` is `owner/repo:<game-slug>`
   — origin × game, the slug taken from `targets[].name` in `pack.json`,
   else from the legacy HD pack's game subfolder — so one origin hosting
   N games yields N slots, and a multi-game zip is expanded by the
   pipeline into N sibling issues carrying `pack:split`. This is what the
   catalog emits today (e.g. `liquidzgit/hdnes:ice-climber`).
3. Else, catalog fallback: `issue-{n}` of the accepted submission. This
   is the only option for gists, `raw.githubusercontent.com` and Google
   Drive links (`scripts/pack_host_allowlist.json`) when the pack has no
   `id` — so for those hosts **product-level deduplication does not
   exist**; only byte-level (`content_id`) does.
4. **Local drops** (a folder or zip the user put in `EnhancementPacks/`,
   `HdPacks/<Game>/` or beside the ROM) with no `id`: `pack_id` is
   `local:<container-name>` (the ADR-0040/0049 discovery key). Two local
   containers with the same `content_id` are one pack (§5). A local
   container whose `content_id` equals a catalog entry's is that catalog
   `pack_id`, not a second choice. The local `content_id` is computed
   **once** and cached under `EnhancementPacks/.cache/` keyed by the
   container's path + size + mtime (recomputed only when those change);
   it is never computed on the synchronous ROM-load path. Until the cache
   is warm the container is treated as `local:<container-name>`; the
   catalog merge happens on the next load. HD trees run to hundreds of
   MB — hashing them at every boot is not acceptable.

**Catalog uniqueness** (product requirement; enforcement is the P.0 ADR).
The catalog holds **one live row per `pack_id`** (§3.6) — never two
revisions of the same product.

**Origin binding (anti-hijack).** A `pack_id` is bound to the **origin**
of its first accepted submission: the `owner/repo` of the pack URL, or,
for hosts without one (gist, raw, Drive), the GitHub login that opened the
issue. A later submission that claims an existing `pack_id` (via `id` in
`pack.json` or via the same `owner/repo`) but comes from a **different
origin** is *not* a revision: it does not compete for the slot, is not
listed, and gets a comment + the `pack:needs-review` label for human
triage — a maintainer may re-bind the origin (author moved repos) or
treat it as a competing pack. Without this rule anyone could publish
`id: contra80s`, `version: 99.0.0` and have §3.6 push it to every
client. The catalog stores the bound origin in mep-meta
(`pack_origin`). Amends ADR-0140/0141 (recorded in both, 2026-08-28).

Actions when the incoming submission is from the **same** origin:

| Incoming vs existing | Meaning | Action |
|---|---|---|
| same `content_id` | byte-duplicate, even if `pack_id`/`version`/`source_sha256` differ | not a second pack; comment "duplicate of #N"; do not list twice |
| same `pack_id`, new `content_id` | new revision of that product | occupies the single slot if it wins §3.6's order; never a picker choice. Triage warns when `version` did not bump |
| different `pack_id`, different `content_id`, same ROM sha1 | competing packs | both listed; the player chooses (§5) |
| different `pack_id`, same `content_id` | same files under two names | byte-duplicate; the existing row wins |

`/revalidate` on the same issue rewrites that issue's **provenance**
(mep-meta: `source_sha256`, recomputed `content_id`, `version`,
`validated_at`) in place. Whether the revalidated revision **occupies the
slot** follows §3.6 — a revalidation that republishes a lower semver does
not displace a higher one already in the slot.

#### 3.4 `version`

Keep `pack.json` `version` (semver, MUST for MEP). It is a **label**, not
an id. On its own it is not sufficient to know "newest" (authors forget to
bump, or bump without changing files) — but it is the best available
*ordering* signal, which is why §3.6 uses it first and `content_id`
(unordered) never.

- `hd-legacy` has no `version`; the catalog and picker show the
  validation date and a short `content_id` prefix instead.
- `version` bumps, `content_id` does not → the revision did not change
  (wrapper-only, or a label bump). The client does not re-download.
- `content_id` changes, `version` does not → still a new revision of that
  `pack_id`. Triage warns; §3.6 still applies.

Do not order competing *products* by `version`.

#### 3.5 Why not one id

| Candidate as "the" unique id | Breaks |
|---|---|
| `source_sha256` (Pack Hash) | wrappers; pack is a subset; two recipes on one zip |
| `content_id` alone | every revision is a new pack; the player is asked to choose between 1.0 and 1.2 |
| `pack_id` alone | cannot tell duplicate bytes from an update; cannot verify an install |
| `version` alone | not unique; authors forget to bump; two products can both be "1.0" |
| ROM sha1 | many packs per game |
| issue number | second submit of the same product; local drops have no issue |

The pair **`pack_id` + `content_id`** is the split npm (`name` + integrity
hash), git (ref + commit) and Docker (`name:tag` + digest) already use. A
single-id scheme is not proposed.

#### 3.6 Current revision — one catalog slot

**`content_id` is equality/integrity only.** The official catalog has
**one live slot per `pack_id`**; whatever occupies that slot *is* current.
The player never sees 1.0 vs 1.2 of the same pack.

When two candidates compete for the same slot, the first rule that
decides wins:

1. **semver** of `pack.json` `version`, when both have a comparable
   version — higher wins. The catalog knowingly accepts that an inflated
   `version` can win **from the same origin** (§3.3 origin binding);
   triage warns, it does not block. `mep_lint` already rejects any
   non-`x.y.z` `version` (error), so "comparable" only fails for
   `hd-legacy`, which has none.
2. Else **`validated_at`** — later wins.
3. Else **issue number** — higher wins (later submission).

History may live in mep-meta / git; it is not a second catalog row and
not a player choice.

**Client**

- Compare the installed `content_id` (from `.mep-install.json`) to the
  catalog slot of the chosen `pack_id`. Different → reinstall, power
  cycle, toast ("Updated …"). Wrapper-only change (`source_sha256`
  changed, `content_id` did not) → do not reinstall. **This amends
  ADR-0138 §37**, whose trigger is `source.sha256`; the P.0 ADR records
  the amendment.
- **No automatic downgrade.** If the installed revision's semver is
  *greater* than the slot's (yank, rollback, author republished an older
  label), keep the install; Advanced may offer "use catalog revision" with
  confirmation. `hd-legacy` (no semver): a `content_id` difference against
  the slot still updates — there is no version number to protect.
- **Pack removed from the catalog** (no slot for that `pack_id` any
  more): keep the install, keep the per-ROM choice, no toast. It stays
  visible in Advanced; the player is not interrupted by a catalog
  decision.
- Reinstall preserves the user's per-container state (`DisabledPacks`,
  per-section flags — both keyed by container name today), since the
  container name does not change on an update.
- Sibling folder still always wins. No catalog write, no update, no
  picker while it is present.

Old trees may remain under `EnhancementPacks/.cache/`; they are not
listed in the picker and are not applied.

### 4. Applying a pack to a ROM

Already shipped, and this GUI must not bypass it:

1. Load ROM → No-Intro sha1 (ADR-0039).
2. `MepPackManager::LoadForRom` scans **sibling folder →
   `HdPacks/<Game>/` → `EnhancementPacks/`** (ADR-0049/0040/0120/0121).
3. A container matches when any `targets[].sha1` equals the ROM, or when
   it is a convention pack named like the ROM (MEP-v1 §2.1 rule 5).
4. Per section, the first pack in lexicographic container order wins,
   unless the user disabled that container. The sibling folder beats
   everything, in every section.
5. `patches[]` apply in place before the console reads the ROM
   (ADR-0044). Missing patch for this sha1 → skip the patch with a log
   line and a UI notice, still load the other sections.
6. Per-section toggles and enable/disable apply on the **next load /
   power cycle**, not live. Pack switch in the player stays a power
   cycle. Do not invent live texture/patch swap in this phase.

F6.4b (Part A, Phase 6) adds: fetch official MEI, match ROM
sha1, download within the host allow-list, sha256-verify the *source*, run
`MepRecipeInstaller`, write into `EnhancementPacks/`, then the scan above
applies it. The `AutoInstallCommunityPacks` toggle and first-run consent
stay in F6.4b (ADR-0138 §38).

This PRD adds, on top of that scan:

- At install time, record `pack_id` + `content_id` in `.mep-install.json`
  next to `recipe_hash`, `source.sha256`, `deps`, `installed_at` (all
  already written by `MepRecipeInstaller::WriteInstallStamp`).
- On the next load of that ROM sha1, follow §3.6: new `content_id` on the
  chosen `pack_id`'s catalog slot → update (unless it would be a semver
  downgrade).
- Sibling folder still always wins. No catalog auto-install, no picker,
  while a sibling pack is present (artist at work).

### 5. Choosing among packs for the same ROM

Not a duplicate. Two `pack_id`s with the same ROM sha1 and different
`content_id`s are competing products (Contra80s vs another Contra HD
pack).

**Player mode**

- 0 catalog/local matches → play with Enhanced Audio + bootstrap only.
  If F6.4b is on and the catalog later gains a match, offer install as a
  toast; never stall the first frame.
- 1 `pack_id` (any number of revisions on disk or in history) → apply
  the catalog slot (§3.6). No picker. Never ask 1.0 vs 1.2.
- 2+ `pack_id`s and no stored choice for this ROM sha1 → the game starts
  **un-enhanced** (Enhanced Audio + bootstrap only) and the picker opens
  over it, once. Picking applies on the power cycle the picker triggers;
  dismissing plays un-enhanced this session and asks again next launch.
  The picker shows name, `author` (from `pack.json`; `hd-legacy` shows
  the submission title), `version` (or validation date + short
  `content_id` for `hd-legacy`), layers (textures / audio / synth /
  patch), licence (or "not declared"), and catalog 👍 as **sort key**, not
  as auto-pick. The choice is remembered **per ROM sha1** — the No-Intro
  sha1 of the ROM as loaded, **before** any `patches[]` apply (§4 step 1
  precedes step 5) — a pack with three `targets[]` is chosen up to three
  times, once per ROM.
- Changing the choice later: overlay → current pack chip → picker.
  Applies on power cycle.
- Mixing section A from pack 1 with section B from pack 2 is **Advanced
  only** (today's Enhancement Packs window and per-section toggles).
  Player picks a whole pack.

**Advanced mode** keeps Tools → Enhancement Packs (MEP)… as it is: list
of matching containers, per-pack enable, per-section flags, lexicographic
default when nothing is chosen. When a per-ROM choice exists (P.3), it
overrides the lexicographic default in Advanced too, and the window shows
which container is the chosen one.

**Local + catalog.** A user-dropped container in `EnhancementPacks/`
whose `content_id` equals the pack already chosen for this ROM is the same
pack, not a second choice. A local container with a different
`content_id` and no `id` joins the picker as `local:<container-name>`
(§3.3 rule 4). The merge only works for packs whose `content_id` is a
tree hash: the *output* folder of a recipe install copied elsewhere
without its `.mep-install.json` cannot be re-associated with the catalog
row (§3.2 — the recipe composite is never derived from the output tree);
it shows up as a `local:` entry. Documented non-goal (§7).

**Where 👍 comes from.** The client has no GitHub access. P.2 adds an
additive MEI field (`votes`, integer, MAY, non-normative like `issue`)
written by the catalog generator from the submission issue's 👍 count.
Clients ignore it for install decisions; the picker uses it only to sort.

### 6. Player chrome and Advanced GUI

One process. `PreferencesConfig.UiMode`: `Player` | `Advanced`.

| | Player (default on a fresh install) | Advanced |
|---|---|---|
| Menu bar | hidden | classic File / Game / Options / Tools / Debug / Help |
| Home (no ROM) | the existing recent-games grid (`RecentGamesViewModel`), always shown; drop a ROM anywhere; **P.7** adds a first-run welcome card (Load ROM CTA, shown once — recents are necessarily empty on a true first run) and, independently, a persistent "Continue: \<last game\>" entry whenever `GameEntries` is non-empty (not gated on first-run — see §8 P.7) | same grid, as today (`GameSelectionScreenMode` keeps its current meaning: what happens when a recent game is clicked; `Disabled` still hides the grid) |
| Playing | game fills the window; the overlay shortcut opens a thin overlay: Resume, Save/Load slot, Pack (if 2+ `pack_id`s, or to inspect the current one), Settings (video / audio / input essentials), Advanced GUI, Quit. **P.7** adds an "Enhancements" panel (quick toggles for Texture/Audio/WideScrn/HiRes/Overclock — no new Save/Load buttons, it reuses the overlay's existing Save/Load slot row) | current menus and windows |
| Overlay shortcut | a new configurable `EmulatorShortcut` (default Esc on keyboard; `KeyCombination` already accepts controller buttons, so a gamepad binding is a config choice, no new code). Default rule in Player: while a ROM runs, Esc opens the overlay and never leaves fullscreen; "Exit fullscreen" is an overlay item. P.4 implements that precedence inside the shortcut config, not by hard-coding | n/a |
| Gamepad navigation | the overlay and the pack picker are fully operable with D-pad/A/B (Avalonia focus navigation; no pointer required). Acceptance of P.4/P.5 includes a keyboard-arrows pass as proxy | n/a |
| Pack feedback | OSD toast on apply/update ("Applied Contra 80s — textures"); pack name on the overlay chip | Enhancement Packs window |
| Debugger, HD Pack Builder, Lua, netplay, movies, cheats, Record Music | not in the overlay; reachable only after switching to Advanced | unchanged |
| Existing `AutoHideMenu` | ignored in Player (no menu bar); left in Advanced preferences | unchanged |

Switching modes is instant and persisted. **Default rule:** when the
settings file already exists at startup and has no `UiMode` key, the
value is `Advanced`, so a current Mesen user is not stripped of Debug on
upgrade. When no settings file exists (fresh unzip), `UiMode` is `Player`.
The key is always written on first save, so the rule only ever runs once.

Do not fork ViewModels. Player hides chrome and routes a small overlay at
windows that already exist (open-ROM dialog, save slots, a reduced
settings page, the pack picker). Advanced is the current `MainMenuView`.

#### 6.1 Enhancements quick-toggle panel (P.7)

A new "Enhancements" entry sits next to Pack/Settings in the overlay,
opening a checkbox grid over existing config — same D-pad/A/B
accessibility bar as P.4/P.5. It does not add its own Save/Load buttons;
the overlay's existing Save/Load slot row already covers that.

| Toggle | Underlying config | Console coverage | Applies |
|---|---|---|---|
| Texture | `EnhancementPackConfig.EnableTextures` | all | needs ROM reload |
| Audio | `EnhancementPackConfig.EnableAudio` | all | needs ROM reload |
| WideScrn | `VideoConfig.AspectRatio` toggled between `Widescreen` (16:9 stretch, `Core/Shared/EmuSettings.cpp:521`) and the value it had before the toggle was turned on (restored, not hardcoded to `NoStretching`/`Auto`, so an Advanced-configured custom ratio survives) | all | immediate (renderer-only) |
| HiRes | `VideoConfig.VideoFilterType` toggled between one curated hi-res preset (candidate `HQ4x`) and the value it had before — same restore-not-clobber rule as WideScrn, so a filter already chosen in Advanced is never silently discarded | all | immediate (renderer-only) |
| Overclock | NES: `NesConfig.PpuExtraScanlinesBeforeNmi`/`PpuExtraScanlinesAfterNmi` (extra vblank scanlines, `Core/NES/NesPpu.cpp:188-190`); GB/GBA: `GameboyConfig`/`GbaConfig.OverclockScanlineCount`; all three toggled between `0` and one curated preset value. **SMS has no overclock knob today** — the toggle stays visible but disabled on SMS so the panel layout doesn't shift per console | NES, GB, GBA (not SMS) | needs reset |

Both enum-backed toggles (WideScrn, HiRes) store the pre-toggle value the
first time they are switched on, so switching off restores exactly what
the player (or Advanced GUI) had configured — never a hardcoded default.
This keeps the panel from drifting out of sync with Advanced's own
settings pages (§6 non-goal: do not fork settings state).

A **Border** toggle (a pack-declared decorative frame around the game
area) is a natural seventh entry here, but it needs a new MEP-v1 field
and a new Core render path first — that is Core/pack work, not chrome,
so it is tracked as its own phase in
Part A, Phase 8 (§4), gated on an ADR. P.7 ships without it; the panel adds the
seventh row once that phase lands.

#### 6.2 Welcome card and "Continue" (P.7)

Two distinct, independent affordances — not one dialog wearing two hats:

- **Welcome card**: shown once, on the very first Player-mode boot (the
  same "settings file missing the `UiMode` key" signal `UiModeDefaultRule`
  already uses, §6). At that point recents are necessarily empty, so its
  only CTA is **"Load ROM"** plus one short line of orientation text. It
  never reappears once dismissed.
- **Continue card**: a persistent, always-shown-when-applicable entry on
  the Player home whenever `RecentGamesViewModel.GameEntries` is
  non-empty — **"Continue: \<most recent game's title\>"**, resuming that
  game. This is not gated on first-run; it is simply what the home shows
  once there is a game to return to, exactly like the rest of the recent-
  games grid it sits alongside.

### 7. Non-goals

- A second executable or a rewrite off Avalonia.
- Live swap of textures/patches without power cycle.
- Auto-picking the 👍 leader when two `pack_id`s match; 👍 only sorts
  the picker.
- A full pack browser (search, extra MEI URLs). Part A defers
  that until the catalog outgrows a list.
- Replacing F6.4b. This PRD consumes it.
- Hosting or committing pack bytes.
- Changing discovery precedence (sibling still wins).
- Product-level deduplication for packs without `id` hosted outside
  GitHub (§3.3 rule 3).
- Re-associating a recipe *output* folder copied without its
  `.mep-install.json` with its catalog row (§5).
- SNES / PCE / WonderSwan / ColecoVision chrome.
- A widescreen mode that reveals more of the playfield (extra per-console
  PPU/VDP decode) — the WideScrn toggle only stretches the existing 4:3
  frame to 16:9 (§6.1); "see more of the game" would be its own
  per-console engine ADR.
- The welcome card reappearing on every boot, or blocking the recent-
  games grid underneath it.

### 8. Slices

Architecture slices need their ADR accepted first. P.3–P.5 run on local
packs and do not wait for F6.4b; catalog install/update in the overlay
(P.6) does.

| Slice | Deliverable | Depends | Acceptance |
|---|---|---|---|
| **P.0** | ADR-0139/0140/0141 (accepted 2026-08-28): (1) `content_id` canonicalisation, the recipe composite, and the two-implementation/parity rule; (2) `pack_id` sources incl. the MEP `id` field and the `local:` fallback; (3) catalog uniqueness (§3.3) + one-slot occupancy (§3.6) as CI/client policy, **amending ADR-0138 §37** (update trigger = `content_id`, no auto-downgrade) | — | **done 2026-08-28** — ADR-0139/0140/0141 accepted; ADR-0141 carries the ADR-0138 §37 amendment |
| **P.1** | `content_id` in `scripts/` (normative) **and** in the Core (`MepPackManager`/`MepRecipeInstaller`), both on the discovered pack root and the recipe composite; `mep_lint` / validate workflow writes it to mep-meta; `.mep-install.json` gains `pack_id`/`content_id`. Goldens: same tree in two wrappers → same id; two recipes on one primary → two ids | P.0 | **done 2026-08-29** — `scripts/mep_content_id.py` (normative) + `scripts/test_mep_content_id.py` (8 checks) + `Core/Shared/EnhancementPacks/MepContentId.{h,cpp}`; `mep_lint --content-id` + the validate workflow's `content-id` step write the tree hash (and the recipe composite for split packs) into mep-meta; `MepRecipeInstaller::WriteOutputs` computes the composite at install time and `WriteInstallStamp` records `pack_id`/`content_id` in `.mep-install.json`; parity fixture `docs/specs/golden/mep-content-id.json` run by `scripts/test_mep_content_id_golden.py` (Python) and core-unit-tests BlocoG (C++), both green |
| **P.2** | Catalog / mep-meta / MEI grow `pack_id`, `content_id`, `version`, `votes` (all additive; unknown-field ignore already required). One live row per `pack_id` (§3.6). Duplicate comment on same `content_id`. `/revalidate` rewrites provenance and occupies the slot only by §3.6 order. Origin binding (§3.3): mep-meta `pack_origin`; different origin → not listed, `pack:needs-review` (label added to `ensure_community_pack_labels.sh`) | P.1 | **done 2026-08-29** — `scripts/pack_id_rules.py` (leaf, stdlib-only): `resolve_pack_id` (MEP `id` → `owner/repo` → `issue-n`), `pack_origin` (§3.3), `slot_winner`/`select_catalog_rows` (§3.6: content-dedup global, per-pack_id origin filter then slot winner — semver → validated_at → issue, deterministic) + `scripts/test_pack_id_rules.py` (8 checks); `mei_catalog_entry.build_pack_entry` gains additive `pack_id`/`content_id`/`votes` (MAY, via `apply_mei_identity`); the validate workflow's mep-meta upsert writes `pack_id`/`pack_origin`/`content_id` and a new `identity-check` step (`scripts/mep_identity_check.py`, `--post`, `continue-on-error`) comments on duplicate `content_id` / foreign-origin claims; `pack:needs-review` label (13th at the time; `pack:split` followed with ADR-0143) added to `ensure_community_pack_labels.sh`; the generator was split per ADR-0138 §35 into `mei_catalog_fetch` (all `gh` reads) + a 123-line orchestrator feeding `select_catalog_rows` (rows still 👍-sorted by `render_table`); AC-2/AC-4/AC-6 verifiers updated for the split and green; `make doc-checks` green |
| **P.3** | Per-ROM-sha1 preference (`pack_id` chosen, `local:` fallback for local drops) persisted in `EnhancementPackConfig`; the **resolution logic** (sha1 → `pack_id`, `local:` fallback, `content_id` merge, lexicographic default) lives in a host-free class under `UI/Logic/` (ADR-0123: `UI.Tests` dual-compiles only `UI/Logic/**`, never `UI/Config`). Picker window usable from **Advanced** (ships before Player chrome). The preference overrides lexicographic order; lexicographic stays the default when no preference exists | P.0 (for the `pack_id` rules) | **done 2026-08-29** — `UI/Logic/PackPreferenceResolver.cs` (host-free): `DerivePackId` (stamped pack_id, else `local:<container>`, ADR-0140 rule 4) + `Resolve` (content_id merge — a container duplicating another's content_id is not a new entry — and preference → winning container, lexicographic default when none/stale); `scripts/`-side `.mep-install.json` identity exposed as pack_id/content_id columns 9–10 of `GetMepPackList` (parser extended, 8-column rows still accepted); `EnhancementPackConfig.RomPackPreference` (romSha1 → pack_id, reset-then-push via the new `ClearPreferredMepPacks`/`SetPreferredMepPack` interop) drives the core's per-ROM preferred pack (`MepPackManager::FindPreferredPack`, consulted before the ADR-0040 order in `GetPackForSection`); Advanced's Enhancement Packs window gained a "Preferred pack for this ROM" combo (content-merged choices + "(default)" clear). UI.Tests: `PackPreferenceResolverTests` (11 checks incl. `local:`, merge, stale, disabled) + 194 total green; `make core`/`ui`/`doc-checks` green |
| **P.4** | `UiMode` + Player chrome: hide menu, overlay + its shortcut, recent games as home, Settings subset, Advanced switch. Existing settings file → Advanced; none → Player | — (chrome only) | done 2026-08-29 — `UI/Logic/UiMode.cs` (`UiModeDefaultRule`: no settings.json → Player, existing keyless file → Advanced via the property initializer; `Configuration.CreateConfig` hooks the fresh path, key written on first save) + 3 tests; `UI/Logic/UiModeShortcutPrecedence.cs` (Player overlay owns its key: a Pause binding on the same combination is suppressed in `PreferencesConfig.ApplyConfig` — the Esc collision resolved in the shortcut config) + 5 tests; `EmulatorShortcut.ToggleOverlay` (default Esc, mirrored in the core enum; core `IsKeyPressed` exempts it from the keyboard-block so it stays reachable in keyboard games); overlay panel (Resume / Save / Load slot / Pack / Settings / Advanced GUI / Quit) on the renderer panel, D-pad nav via focus, opened paused; menu hidden in Player (MouseManager + VM, AutoHideMenu ignored); recent-games grid always shown as Player home; `PreferencesConfig.UiMode` combo in the Preferences tab for the Advanced→Player switch. Pending (manual): Player cannot reach Debug without switching, Esc-while-playing passes. §6 "reduced settings page" **shipped 2026-08-29**: the overlay's Settings opens `ConfigWindow(playerMode: true)` showing only the essentials tabs — `UI/Logic/ConfigWindowTab.cs` (enum moved host-free) + `UI/Logic/PlayerSettingsEssentials.cs` (clamp, +9 UI.Tests), `ConfigViewModel.PlayerMode` hides the Emulation/console/Preferences tabs and the Reset/Open-Folder bar, initial tab clamps to Audio. Player Settings GUI run still pending. **Manual GUI pass done 2026-09-01**: fresh-launch UiMode=Player confirmed (no prior settings.json), Esc opened the overlay over a running game |
| **P.5** | Player pack UX: toast, overlay chip, picker from §5 wired to P.3; un-enhanced start while the picker is open | P.3, P.4 | done 2026-08-29 — `UI/Logic/PlayerPackPicker.cs` (host-free `ShouldOpen`: sibling pack always suppresses §4, <2 distinct pack_ids → slot applies/never ask, effective stored preference → silent apply; `DistinctPackIdCount` over the §5 content-merged candidates) + 8 tests; picker panel over the un-enhanced game (name/author/version/layers/licence from `GetPackListText` columns, sorted by name; pick stores the per-ROM preference P.3 and power-cycles, dismiss stores nothing → asks again next launch; Esc dismisses); overlay Pack button became the current-pack chip (opens the picker even with a stored choice — §5 "changing the choice later" — else the pack window); "Applied …" OSD toast via `EmuApi.DisplayMessage` on apply in Player, suppressed while the picker is open. UI.Tests 210 (8 new), UI osx-arm64 0 errors, firewall OK. Pending (manual): keyboard-arrows-as-gamepad-proxy pass, toast noise judgement. **Picker/dismiss/chip-reopen flow manually verified 2026-09-01** (two centrally-installed test packs, distinct `pack_id`/`content_id`, no sibling folder): picker opened with both candidates on first launch, picking either persisted `RomPackPreference` and power-cycled with that pack's textures loaded, and the overlay chip reopened the picker to switch the choice (verified switching A→B actually changed which container's textures loaded, not just the stored id). Also found and filed **issue #150**: a bootstrap sibling folder holding only the F5 recorder's `auto/` layer (no human-authored files) is still treated as a "sibling pack" by `ShouldOpen`/`OpenPlayerPackPickerForChange`, so once the bootstrap has written to `<rom>/auto/` the picker never opens again on that ROM |
| **P.6** | Player overlay talks to F6.4b install/update using §3.6 (`content_id` trigger, no auto-downgrade, removed-from-catalog keeps install); `votes` sorts the picker | P.5, F6.4b | done 2026-08-29 — `UI/Logic/CommunityCatalogUpdateDecision.cs` (host-free §3.6 verdict: `Updated` on content_id diff, `WrapperOnly` no-reinstall on source-only change, `NoDowngrade` when the installed semver is newer (hd-legacy has none), `RemovedFromCatalog` keeps the install, `UpToDate`/`NotInstalled`; `ReadStampFields` + numeric `CompareSemver`) + 15 tests; `CommunityPackCatalogEntry` now deserializes the P.2 additive `pack_id`/`content_id`/`votes`; the F6.4b coordinator's reinstall gate switched from the ADR-0138 §37 source.sha256 trigger to the §3.6 content_id decision (container name unchanged, so `DisabledPacks`/per-section flags survive an update; "removed slot" is the fetch-returns-null path, already silent); the picker sorts by community 👍 (`votes` desc, then name — local-only packs fall back to name). UI.Tests 225 (15 new), UI osx-arm64 0 errors, firewall + doc-checks OK. Pending (manual): catalog update end-to-end on a real fetch, "Updated …" toast wording |
| **P.7** | Enhancements quick-toggle panel (§6.1: Texture/Audio/WideScrn/HiRes/Overclock, restore-not-clobber semantics on the two enum-backed toggles) + welcome card and persistent Continue card on the Player home (§6.2) | P.4 (overlay), P.5 (home) | **done 2026-09-01** — `UI/Config/PlayerEnhancementsConfig.cs` (new, no Core counterpart: `WideScrnPriorAspectRatio`/`HiResPriorFilter` restore-not-clobber state, `WelcomeCardDismissed`); `UI/Logic/PlayerEnhancementsToggle.cs` (host-free): generic `ToggleEnumPreset<T>` (stash-then-restore for WideScrn/HiRes, never a hardcoded default), NES/GB/GBA overclock on/off + curated presets (NES 300 before-NMI scanlines per the app's own `lblOverclockHint`; GB/GBA 40 additional scanlines, no equivalent in-app guidance existed so this is a conservative, easily-retuned constant), `SupportsOverclock` (NES/GB/GBA only, SMS has no knob), `ShouldShowWelcomeCard`/`ShouldShowContinueCard` + 18 UI.Tests (`UI.Tests/Config/PlayerEnhancementsToggleTests.cs`). On/off state for all 5 toggles is derived from config that already exists (`EnhancementPackConfig.EnableTextures`/`EnableAudio`, `VideoConfig.AspectRatio`/`VideoFilter`, the per-console overclock field) - never a second source of truth. `MainWindowViewModel`: `IsEnhancementsPanelVisible` + the five `Toggle*`/`OpenEnhancementsPanel`/`CloseEnhancementsPanel` methods (same replace-the-overlay shape as the P.5 picker, Esc precedence chained the same way); Texture/Audio apply via `ReloadRom()`, Overclock via `PowerCycle()`, WideScrn/HiRes immediately via `VideoConfig.ApplyConfig()`. `MainWindow.axaml`: "Enhancements" overlay entry + a `PlayerEnhancementsPanel` checkbox-grid border (Overclock checkbox disabled, not hidden, on consoles with no knob); Welcome/Continue cards added around `RecentGamesViewModel`'s `StateGrid` DataTemplate, gated on `UiMode == Player` and `Mode == RecentGames` (never on Advanced's game-selection screen or the Save/Load state screens sharing the same DataTemplate) - Welcome's one CTA ("Load ROM", reusing the existing `EmulatorShortcut.OpenFile` dialog) is also its own permanent dismissal; Continue resumes `GameEntries[0]`. `UI.Tests` 373 (18 new) green, `dotnet build UI` osx-arm64 0 errors/warnings. Border (a 7th toggle) stays out of scope; tracked in Part A, Phase 8, gated on its own ADR. Pending (manual): GUI pass on a real display (toggle each switch, confirm apply semantics and WideScrn/HiRes restore, confirm Welcome/Continue on a fresh vs. populated `RecentGamesFolder`) |

### 9. ADR map

| Topic | Status | Meaning |
|---|---|---|
| ADR-0139 — `content_id` algorithm (tree canonicalisation, recipe composite, excluded files, `version` string excluded, two implementations + parity) | **accepted** (2026-08-28) | P.1 cannot start without it |
| ADR-0140 — `pack_id` (MEP `id` field; `owner/repo`; `issue-n`; `local:<container>`) + catalog uniqueness + origin binding (amended 2026-08-28) | **accepted** (2026-08-28) | P.2/P.3 cannot start without it. §3.6 is accepted product text — the ADR specifies enforcement |
| ADR-0141 — one live slot per `pack_id`; amends ADR-0138 §37 (client update trigger `source.sha256` → `content_id`); no auto-downgrade; removed slot keeps install | **accepted** (2026-08-28) | P.6 shipped 2026-08-29 on this trigger; ADR-0138 §37's own text still awaits the in-place note (Part A slice D5) |
| ADR-0143 — one slot per **game**: `pack_id` = origin × game; multi-game zip → N packs + N `pack:split` sibling issues | **accepted** (2026-08-29) | amends §3.3 rule 2 above and ADR-0140 source 2; eight of the nine LiQuiDz siblings were later removed from the catalog as audio-only NEA (Part A slice D4) |
| Player chrome (`UiMode`, overlay contents, overlay shortcut, upgrade default Advanced) | **needed only if** P.4 finds trade-offs beyond §6 | P.4 |
| Enhancements quick-toggle panel + welcome/Continue cards (§6.1, §6.2) | not needed — UI over config that already exists | P.7 |
| ADR-0039/0040/0044/0049/0120/0121 | accepted | precedence and ROM hash-matching do not change |
| ADR-0138 (except §37 as above) | accepted | F6.4b is the network installer this shell consumes |

### 10. Risks

| Risk | Mitigation |
|---|---|
| `content_id` treated as the pack id | §3.5–§3.6; picker and preference key off `pack_id`; `content_id` is equality/integrity only |
| Catalog yank / republished older semver | no auto-downgrade (§3.6); Advanced confirms |
| Authors omit `id` / `version` (`hd-legacy`) | fallbacks in §3.3/§3.4; keyed by origin repo or issue; picker shows date + hash prefix |
| Two issues, same product, different `pack_id` fallbacks (non-GitHub hosts) | `content_id` still collapses byte-duplicates; remaining cases open the picker (safe default); documented non-goal until `id` is common |
| Inflated `version` wins the slot | accepted trade-off (§3.6 rule 1) **within one origin**; triage warns; no auto-downgrade protects installs |
| Third party claims an existing `pack_id` (`id` or `owner/repo` spoof) with a high `version` | origin binding (§3.3): different origin never occupies the slot; `pack:needs-review` for a human |
| Hashing local HD trees stalls the ROM load | `content_id` of local containers cached by path+size+mtime, computed off the load path (§3.3 rule 4) |
| Overlay unusable from the couch | overlay shortcut bindable to a controller button; overlay/picker navigable by D-pad (§6) |
| Recipe identity without dep bytes | composite in §3.2; computed at install time from the primary bytes, stored, not re-derived |
| `scripts/` and Core hashers drift | parity fixture in P.1, same pattern as ADR-0138 §39 |
| Local-pack identity ambiguous | `local:<container>` rule (§3.3 rule 4); `content_id` merges local ↔ catalog |
| Player chrome accidentally ships a second UI stack | P.4 acceptance: no new debugger/settings rewrite; hide and overlay only |
| Esc collides with existing shortcuts | configurable `EmulatorShortcut`; P.4 resolves in shortcut config |
| Scope collision with F6.4b | P.6 waits; P.3–P.5 work on local packs |

### 11. Open questions

None for P.0 — the four questions this section held (tree-hash
canonicalisation; MEP `id` field now; duplicate-submit policy; silent
`local:` → catalog `pack_id` migration) were closed by ADR-0139/0140/0141
on 2026-08-28 (hash: ADR-0139; `id` as MEP v1.4 SHOULD, comment + close
the newer duplicate issue, silent migration: ADR-0140). The MEP-v1 spec
bump itself has **not** landed — MEP-v1 is still v1.3 with no `id` in
§3.1 (Part A slice D2). New questions go
here only when a slice surfaces a trade-off §3–§6 do not settle.

### 12. References

- Parent roadmap: Part A (this document)
- Discovery / precedence: ADR-0040, ADR-0049, ADR-0120, ADR-0121
- ROM hash: ADR-0039, MEP-v1 §4
- Catalog / recipe / auto-install: ADR-0138 (§37–§39), MEI-v1 §2.2,
  MEP-recipe-v1
- Host allow-list: `scripts/pack_host_allowlist.json`
- Install stamp: `Core/Shared/EnhancementPacks/MepRecipeInstaller.cpp`
  (`WriteInstallStamp`)
- Current pack UI: `UI/ViewModels/EnhancementPacksViewModel.cs`,
  `UI/Config/EnhancementPackConfig.cs`
- Current chrome: `UI/Views/MainMenuView.axaml`,
  `UI/Windows/MainWindow.axaml`, `UI/ViewModels/RecentGamesViewModel.cs`
