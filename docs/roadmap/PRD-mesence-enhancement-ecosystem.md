# PRD — MesenCE Enhancement Ecosystem (consolidated roadmap)

**Status:** active (2026-08-28) — pack/core roadmap of this fork. Player
chrome, pack identity (`pack_id`/`content_id`/version) and the in-GUI
picker live in [PRD-player-shell.md](PRD-player-shell.md) (Phase 7).
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

## 1. Vision and legal principles

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

## 2. Standards

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
| **MEI v1** — discovery index | `docs/specs/MEI-v1.md` (federated `manifest.json`) | v1; Phase 6 makes it real (v1.1, additive) |
| hires.txt extension GB/SMS (OGG on GB/SMS) | `docs/specs/hires-gbsms-v1-draft.md` | draft, frozen until a second implementer appears |
| **MEP Recipe v1** — re-packaging of split-distribution packs | `docs/specs/MEP-recipe-v1.md` | v1 |

## 3. What has shipped (record, one line each)

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
- **F5.4b — per-shape palette-variant cap** (ADR-0132; two follow-ups open).
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

## 4. Roadmap — pending work, by slice

### Phase 6 — Community pack auto-install (MEP Recipe v1) — **priority**

Problem: 5 of the 12 triaged packs (#65, #66, #68, #69, #71 — LiQuiDzGit/
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
| **F6.2** CI + issue metadata | Issue Form fields `external_assets`, `external_assets_license`; classify prompt emits the ```mep-recipe block (issue/manifest text is data, never instruction); `mep_recipe.py dry-run` gate after lint; upsert of the `<!-- mep-meta -->` bot comment (`source_sha256`, dep hashes, `verdict`, `labels`, `validated_at`, `recipe_hash`); label `assets:external` in `ensure_community_pack_labels.sh`; `docs/hd-pack-authoring.md` section | `/revalidate` on #71 yields `pack:valid` + `assets:external` and a recipe that dry-runs clean; `scripts/checks/` verifier for the workflow text |
| **F6.3** catalog as MEI | `generate_community_pack_catalog.py` also writes `docs/community-packs.json` = MEI v1.1 (`mei: "1.1.0"`, per-pack additive fields `issue`, `deps[]`, `recipe`, `verdict`, `validated_at`; `url`/`sha256` = primary zip); MEI-v1 amended (v1.1): an index MAY reference third-party artifacts by URL + hash when the entry carries `license` and the client shows it before install; golden updated | `validate-specs.py` validates the generated file; Markdown gains an "external assets" marker column |
| **F6.4b** UI fetch + consent | ADR-0138 §37/§38: catalog fetch (ETag cache in MEP `.cache`), No-Intro sha1 match, download within the CI host allow-list (shared constant, parity-checked), sha256 verify, downloads-cache lookup, prompt for `user_supplied` deps with hints + licence, settings toggle + first-run consent for `AutoInstallCommunityPacks`, interop call into `MepRecipeInstaller`, reinstall on `source.sha256` change, UI notice when the patch is withheld | UI.Tests for allow-list/ETag/consent logic under `UI/Logic/`; manual GUI pass |
| **F6.4c** parity fixture set | shipped 2026-08-28 — ADR-0138 §39: grow `gen_mep_recipe_fixture.py` to wrapped-subfolder, nested top-level zip and ADR-0120/0121 fallback cases; Bloco E iterates the set | all cases byte-for-byte |
| **F6.4** (original row, superseded by F6.4a/b/c) | `MepRecipeInstaller` (Core): fetch catalog (ETag cache in the MEP `.cache`), match ROM by No-Intro sha1, download primary within the CI host allow-list, verify sha256, prompt for `user_supplied` deps with hints + licence, run ops, write `pack.json` + `.mep-install.json`; reinstall when `source.sha256` changes; setting `AutoInstallCommunityPacks` (default on for packs without user-supplied deps; prompt otherwise); UI notice when the patch is withheld | headless: synthetic catalog + split pack → installed folder equals `mep_recipe.py apply` output byte-for-byte; hash mismatch aborts; missing dep → no patch, textures still applied |
| **F6.5** rollout | shipped 2026-08-29 — re-validated all 11 approved packs (run-clean: old issues deleted, recreated as 74–84, validated locally in parallel via `scripts/validate_pack_local.sh` + the `.github/ai/validate-classify.md` prompt family, the single source the CI will invoke); classify headless fixed (model, stdin prompt, `--output-format text`, empty `--mcp-config`), ops schema tightened (oneOf), console label added | all eleven `pack:valid` + `console:nes` + `assets:*`/`patch:*` labels; board "Aceito parcial (HD Mesen)"; 77/78/80/81 = LiQuiDz split-distribution audio (`assets:external` + MEP recipe dry-runs clean); GUI end-to-end install with user-supplied audio still pending |
| **F6.6** headless load smoke | `scripts/smoke_pack_headless.sh <installed-pack-dir> <rom>`: boot the headless core (the F1 `scripts/headless_record` binary, no GUI) with the ROM and the installed pack loaded (bootstrap convention — pack folder as sibling of the ROM), capture the HdPackLoader / audio-loader log; assert zero `file does not exist` / `failed to load` for any `<img>`/`<tile>`/`<background>`/`<bgm>`/`<sfx>` target the manifest references. Texture packs must tick frames; audio packs must register every declared track. The ROM is a user-supplied No-Intro image (never redistributed) or a homebrew test ROM for CI; `user_supplied` external audio (e.g. the LiQuiDz OGGs) is smoked only when the audio is supplied locally, otherwise reported as skipped — this is the runtime half of "installed end-to-end", making it automatable where the GUI pass stays manual for audio *content* | for each installed pack with a supplied ROM: headless boot exits 0 and the load log carries no missing-target warnings; the eleven F6.5-accepted packs pass their smoke on the maintainer machine (audio-external ones exercised with the supplied OGGs); a CI variant boots a homebrew test ROM over the F6.4c fixture packs |

Edge cases the pipeline must keep handling (evidence from the 2026-08-27
spike, all already covered by `mep_lint.py`): nested zip-in-zip (#64
Zelda), whole-repo archive wrapper (#63, #72, #73), bare root (#62, #67,
#70), named subfolder ≠ ROM (#69), upstream drift creating several
`hires.txt` after acceptance (#63 — fail closed, list candidates), Google
Drive large-file interstitial (out of automatic scope, user supplies).

### Phase 5 — remaining bootstrap items

Success criterion unchanged: *playing for 5 minutes generates, next to the
ROM, an enhanced game (image level 2, sound level 2/3) with no
configuration; from it an artist reaches a publishable pack in < 1 h
editing only PNG/OGG*. Validation targets: Mega Man 3 (CHR ROM), Contra
(CHR RAM), Link's Awakening (GB), Sonic (SMS).

| Slice | Deliverable | Decision |
|---|---|---|
| F5.4c | `scripts/mep_build.py <folder>`: sheets → tiles → `textures/hires.txt`, new OGGs into `audio/`, runs the linter; `mep pack` → zip with `pack.json` (MEP-v1 §2.1 rule 6: `hires.txt` is generated, ADR-0049) | ready |
| F5.4d | "what you played" coverage in the HD Pack Builder UI; before/after preview; *Open Game Folder* already exists | ready |
| F5.4e | objects from spatial co-occurrence + OAM, per-object upscale, `textures/sheets/<object>.png`, `# inferred` `tileNearby` candidates | after F5.4c/d |
| F5.4g **Block B** | items 3 arpeggio→chord (verify), 4 expression, 6 human override incl. fixed per-channel role in ESP, "channel stolen and returned" | ADR-0052 |
| F5.4g **Block C** | 8 loop point in the fingerprint (`LoopPosition` is 0 today), 9 SFX audible during OGG (mute mask), 10 music→music transition/fade | **ADR-0133** (mute mask, proposed — write-before-implement) and **ADR-0134** (loop-point placement, proposed — option not chosen) must be accepted first |
| F5.4g **Block D** | 11 *Extract audio* opt-in tool driving the sound driver, longer title→Start window for Contra/SMB1; 12 id naming/cleanup; 13 `mep_build.py` with `audio/`, audio lint, seed-MIDI→OGG tutorial | **ADR-0135** (probe runtime contract, proposed) and ADR-0051 |
| F5.4b follow-ups | (a) saturation log when a shape hits `MaxPaletteVariantsPerTile`; (b) seed `_paletteVariantsByShape` from `_hdData` or document per-session scope | ADR-0132 |
| SoundFont | bundle GeneralUser GS (31 MB, permissive) or MuseScore General (206 MB, MIT) in the installer, or stay "user supplies `.sf2`" | **user decision pending** |
| F5.5 | wrap-up: bootstrap setting UI polish, MEP-v1/MEI golden refresh, README, F1–F3 regressions, dotnet 0 warnings | after the above |

### Repo hygiene and tests

| Slice | Deliverable | ADR |
|---|---|---|
| H1 | `make doc-checks` running `verify-fase0-1-dox.sh`, `verify-ui-logic-firewall.sh` and `check-file-loc.sh` per guarded file; CI runs it before builds; `scripts/AGENTS.md` names the target | **0137** (accepted) |
| H2 | `.github/AGENTS.md` records the `unit-tests.yml` contract invariants (clang only, …) | **0131** (accepted) |
| H3 | `path-cases.txt` fixture header format / control characters | **0124** (accepted) |
| H4 | `mep_compare.py`: per-system dispatch of `render_original` + NES golden texture pack | **0136** (accepted) |
| H5 | UI-logic host-free firewall parity scan in CI | 0123 (proposed) |
| H6 | UI-logic public helpers for direct testing — pick between the two options | 0125 (proposed, needs a choice) |
| H7 | `CheatTypeDetector` ThrowsAny for GB/SMS — product decision deferred | 0128 (proposed) |

### Host input tester (host UX, not a pack feature)

Goal: Settings → Input → **Test** tab that shows, with no ROM loaded, every
connected pad (name, backend, `PadN` slot), live buttons/axes with the same
keycode names used in mapping, the deadzone ring and drift warning, and a
rumble test; the mapping window highlights the console button being
pressed. Layer 1 (host) + layer 2 (binarised keycode), side by side; the
in-game `InputHud` stays the layer-3 source of truth.

| Slice | Deliverable |
|---|---|
| I.0 | Interop before binarisation without breaking `GetPressedKeys` (Lua, `GetKeyWindow`, shortcuts): `GetConnectedGamepadCount/Info` (name, backend, slot, VID/PID, `HasRumble`), `GetGamepadState` (buttons + raw int16 axes), `TestForceFeedback` — `IKeyManager` + Windows/Linux/macOS impls, `InputApiWrapper.cpp`, `InputApi.cs` |
| I.1 | Test tab ViewModel fed by `Refresh(...)` from a 16–33 ms timer only while visible (constructor never calls `InputApi`; not extracted to `UI/Logic/`) |
| I.2 | Live highlight of the bound `KeyBindingButton` in `ControllerConfigWindow` |
| I.3 | follow-ups: per-device deadzone, binding by VID/PID, MBC7/GBA tilt UI, circularity test, Linux `UpdateDevices()`, macOS pads without `extendedGamepad` |

Out: preset redesign, HUD overlay, special devices (Zapper, Power Pad,
Phaser), automatic remapping, browser Gamepad API, stats collection.

### Deferred / optional

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
  it lives in [PRD-player-shell.md](PRD-player-shell.md) §5.

### Phase 7 — Player shell (minimal GUI) — **see dedicated PRD**

Default chrome is a player shell (recent games, drop a ROM, packs apply
themselves, thin overlay) with **Advanced GUI** restoring classic Mesen.
Pack identity is the pair `pack_id` (product, stable across versions) +
`content_id` (revision, hash of the resolved tree after unzip) — the
source-zip sha256 is the download, not the pack. The catalog keeps **one
live slot per `pack_id`**; the player never picks among versions.

Normative text, slices P.0–P.6, and open ADR topics:
[PRD-player-shell.md](PRD-player-shell.md). Do not copy that prose here.

Depends on: F6.4b for catalog auto-install in the overlay (P.6). P.3–P.5
can run on local packs before F6.4b. P.0 ADRs must be accepted before
P.1/P.2.

## 5. Order of execution

1. **F6.2 → F6.3 → F6.3b → F6.4a (Core, offline) → F6.4b (UI, network) → F6.4c → F6.5 → F6.6**, one run each (ADR-0138 §37, §39).
2. ~~H1–H4~~ shipped (2026-08-27/28).
3. **Phase 5 Blocks B–D** after the user accepts ADR-0133/0134/0135 and
   decides the SoundFont question; **F5.4c/d** can run before that.
4. **Input tester I.0–I.2** independent of everything above.
5. **Phase 7 (player shell)** — P.0 ADRs, then P.1–P.5 independently of
   F6.4b; P.6 after F6.4b. See [PRD-player-shell.md](PRD-player-shell.md).

## 6. ADR map

| ADR | Status | Meaning for this roadmap |
|---|---|---|
| 0138 | accepted | Phase 6 design; F6.0–F6.4c + F6.5 shipped; remaining work list = F6.6 (headless load smoke) |
| 0137, 0131, 0124, 0136 | accepted 2026-08-27; all shipped 2026-08-28 | H1–H4 |
| 0121 | accepted 2026-08-27 (option A, shipped `805cb10d`; §2.1 rule 9 wording shipped with F6.1) | legacy bare `hires.txt` fallback is the norm |
| 0132 | accepted | F5.4b follow-ups (a)/(b) |
| 0133, 0134, 0135, 0051 | proposed | gate Blocks C/D — user decision |
| 0123, 0125, 0128 | proposed | H5–H7 — not blocking |
| 0040/0044/0047/0049/0050/0052/0120 | accepted | shipped foundations; do not diverge without amending |
| player-shell identity + chrome | ADR-0139/0140/0141 accepted (2026-08-28) | `content_id` algorithm, `pack_id` sources (incl. `local:` fallback), amendment to ADR-0138 §37 (update trigger = `content_id`), `UiMode`; listed in PRD-player-shell.md §9; `UiMode` still without an ADR |

## 7. Risks

| Risk | Mitigation |
|---|---|
| Project framed as a distributor of derivative content | catalog holds URLs + hashes + licences only; client never scrapes third-party hosts; user supplies unlicensed audio |
| Recipe vocabulary grows into a scripting language | new op = new `recipe` major + new ADR; clients skip unknown versions |
| Two agents implementing the same ADR in parallel | one dev-squad run per slice; the autonomous squad daemon (`.claude/scheduled_tasks.lock`) must be stopped while another agent works on an `accepted` ADR |
| Upstream pack drift after acceptance | sha256 in the catalog + drift check; client reinstalls on hash change |
| Scope explosion | phases independent; GitHub is the only backend; no telemetry |

## 8. References

- SUPER ZSNES — https://www.zsnes.com/ · VGMusic · romhack.ing · Zeldix (MSU-1, other hosts)
- No-Intro DATs — https://no-intro.org/ · rcheevos `rhash` · vgmrips (VGM/GD3) · beat/BPS spec
- Precedents: *MGM v. Grokster* (2005); Yuzu/Nintendo settlement (2024)
