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
the shipped record, and the pending slices (Phase 9 F9.18, the Phase 10
feasibility spikes, plus the hardware-gated residue of the shipped phases). Part B is the
default-GUI roadmap: player
chrome, Advanced GUI, pack identity (`pack_id`/`content_id`/version),
duplicates, the pack picker, and the quick-enhancements panel. The two
Parts intentionally do not duplicate each other's prose: each holds its own
header block, slice table, and ADR map.

---

## Part A — Enhancement ecosystem (pack/core)

**Status:** active (2026-09-09) — pack/core roadmap of this fork. Player
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
**Decisions:** `docs/adr/` — `accepted` ADRs are binding; §6 lists the ones this roadmap depends on ·
**Process:** one task per **slice** (F6.1, F6.2, …), never a whole phase or the whole PRD in one run — decomposing multi-phase work failed twice. Settle the slice's ADRs before running it. A slice is done when its acceptance checks pass headless and the header of this file is updated.

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
   presets, catalogs (URLs + hashes + licenses), tools. Derivative content
   is *referenced*, never hosted or committed.
3. **The emulator is content-dumb:** no bundled derivative material, no P2P,
   no monetisation (*MGM v. Grokster*, Yuzu 2024).
4. **Hosts never execute pack content as code** (MEP-v1 §6). Patches and
   recipes are declarative data interpreted by a fixed vocabulary.
5. **No LLM in the client.** LLMs run only in CI (the community-pack classify
   step); whatever they emit is validated by deterministic scripts before a
   human or the client sees it. `Core/`, `UI/` and the installer never call
   a model, hold a key or carry a prompt. An external tool under `scripts/`
   is not the client, but what it may send off the machine is governed by
   ADR-0154, not by this principle (see Phase 10).

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
| ROM identification | No-Intro sha1 (iNES header-size normalization, ADR-0039/0044) | shipped |
| Textures | HDNes `hires.txt` (Mesen is the reference implementation) | shipped, NES/GB/SMS |
| NES replacement audio | OGG via HD pack `<bgm>/<sfx>` + APU fingerprint trigger (ADR-0047) | shipped |
| Patches | IPS/BPS in `patches[]` by sha1 (ADR-0044) | shipped |
| Audio log / score | VGM 1.71 + GD3, SMF type 1 + GM | shipped (F1) |
| **ESP v1** — Enhanced Synth Preset | `docs/specs/ESP-v1.md` | v1 |
| **MEP v1** — pack container | `docs/specs/MEP-v1.md` (§2.1 folder-form, sibling folder, `auto/` layer; §3 `pack.json` optional; §4 hash; §5 sections; §6 security) | v1.6 (v1.1 `patches[]` + folder-form/`auto/`; v1.2 `targets[].md5`; v1.3 rule-9/§6 as-code wording, ADR-0121/0138; v1.4 root `id`, ADR-0140; v1.5 `border`, ADR-0149; v1.6 root `generated`, ADR-0154; all additive) |
| **MEI v1** — discovery index | `docs/specs/MEI-v1.md` (federated `manifest.json`) | v1.4 (Phase 6 made it real as v1.1; D3 v1.2 `rom.sha1s`, D13 v1.3 `pack_id`/`content_id`/`votes`, F6.8 v1.4 `errata` §2.6, all additive) |
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
  with T1 stagnated; recovered per §40. GUI flow exercised against the
  live catalog by F6.5 on 2026-09-04; the first-run consent dialog was later
  removed by F6.7 (ADR-0146).
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
- **F5.4c — `mep_build.py`** (2026-08-29): sheets → tiles → `textures/hires.txt`,
  new OGGs into `audio/`, the linter as the gate, `pack` → deterministic zip
  with a generated `pack.json`, `rename-audio-id`; `scripts/test_mep_build.py`.
- **F5.4d — coverage report + Before/After preview** (2026-08-29):
  `HdPackBuilder::GetCoverageReport()` surfaced in the builder window;
  `HdPackPreviewWindow` shows each sheet beside its `*.orig.png` twin.
- **F5.4e — objects from spatial co-occurrence** (2026-08-29): union-find over
  8 px neighbours → `textures/sheets/object<NNN>.png` + inert `# inferred`
  `tileNearby` candidates. Never emitted a sheet on a real game; the criterion
  was retired by Phase 9 F9.3, the inert-condition contract kept.
- **F5.4g Block B — arpeggio→chord, expression, `FixedRole.<ch>` override,
  channel-steal hand-back** (ADR-0052, 2026-08-29); regression pinned by
  `core_unit_tests` Bloco L against a PCM golden (2026-09-03).
- **F5.4g Block C — loop point (ADR-0134), SFX mute mask (ADR-0133), 40 ms
  BGM crossfade (ADR-0142)** (2026-08-29); the listening checks replaced by
  Blocos I/J/K (2026-09-03; bug #151, a block-stepped fade, fixed on the way).
- **F5.4g Block D — Extract Audio tool + GUI wiring** (ADR-0135/0051,
  2026-08-29): `spike_sound_driver` productised (frame and wall-clock budgets,
  guaranteed no-op), detached spawn from the HD Pack Builder button (no-op
  path confirmed on a real display 2026-09-01); `audio_cleanup_suggest.py`;
  "Seeding audio" tutorial in `docs/hd-pack-authoring.md`.
- **F5.5 — wrap-up** (2026-08-29): last pack-UI strings localized, goldens
  refreshed and wired into `make doc-checks`, README Player-mode section,
  F1–F3 regressions green, `dotnet build UI` 0 warnings.
- **SoundFont** (decided 2026-08-29): bundle GeneralUser GS (31 MB,
  permissive) in the installer — waits on the installer's first release.
- **F6.5 — rollout** (2026-08-29 → 2026-09-04): accepted set re-validated
  (current issues #128–#148; catalog at 11 rows), classify prompt
  single-sourced from `.github/ai/validate-classify.md`, the six
  `liquidzgit/hdnes` submissions resolved by ADR-0143, audio-only NEA siblings
  de-listed (ADR-0148); guided GUI install acceptance run 2026-09-04
  (`docs/validation/f65-install-acceptance-checklist.md`), finding and fixing
  #155 (→ ADR-0151) and #156. Only the native OS file-picker step stays
  manual; CI live validation re-enable (`LIVE_VALIDATION_ENABLED`) deferred
  by user decision 2026-08-29.
- **F6.6 — headless load smoke** (2026-08-29): `scripts/smoke_pack_headless.sh
  <pack> <rom>` asserts zero missing-target warnings; CI variant over the
  F6.4c fixtures in `make doc-checks`; `MepPack::Parse` accepts an empty
  section `path` (MEP-v1 §3.2).
- **F6.7 — auto-load every accepted pack** (ADR-0146, 2026-09-01): first-run
  consent gate removed, `AutoInstallCommunityPacks` the single switch;
  confirmed on Donkey Kong #144 (catalog art wins over the bootstrap auto
  pack); macOS open-documents routing fixed (#149).
- **F6.8 — known-missing errata** (ADR-0152, 2026-09-04):
  `docs/community-packs/errata/<sha256>.json` read by one parser
  (`scripts/mep_errata.py`) for both gates; provenance in MEI v1.4 `errata`,
  the `†` footnote and the Player picker; `pack:known-missing` applied by
  `apply-verdict`. Returned `issue-139`, `issue-137` and `issue-148` to the
  catalog; found and fixed #160 (log ring) and #161 (`Customization/` roots,
  ADR-0121 amended).
- **H5–H7** (ADR-0123/0125/0128, 2026-08-29): UI-logic firewall parity scan
  in CI; public test-facing helpers; `CheatTypeDetector` ThrowsAny (the GB/SMS
  product decision still deferred).
- **H8 — `NES_ONLY`/`LessUI` build modes** (ADR-0158, 2026-09-05): measured
  and **declined** — the prior art is C#-only and none of its exclusions
  applies to this tree; the one win kept is `core-unit-tests` compiled per
  translation unit with `-MMD -MP` (39.3 s → 9.7 s cold).
- **H9 — `HeadlessInputEngine`** (ADR-0127 pattern, 2026-09-05): the stateful
  headless input surface tested against a fake core, `core_unit_tests` Bloco R.
- **H10 — accuracy suite as a regression gate** (ADR-0162 `proposed`,
  2026-09-05): `scripts/accuracy_compare.py` runs AccuracyCoin against one
  binary in four arms (`vanilla`/`builder`/`hdpack`/`mep`) and requires
  identical frame checksums; an identity pack makes the texture arm real;
  proved red two ways; ROM not vendored; not in CI yet, by decision.
- **D1–D13 — documentation integrity** (audit 2026-09-01; all shipped
  2026-09-01/03 except D8 §3): ADR files restored + `verify_adr_refs.py`
  (D1); MEP-v1 v1.4 `id` (D2); MEI v1.2 `rom.sha1s` (D3); ADR-0148 (D4);
  ADR-0138/0143/0049 amended in place (D5, §4 note 2026-09-07); consent
  plumbing removed (D6); ADR-0139–0145 Consequences/Alternatives filled (D7);
  ADR-0120 §4 covered by `core_unit_tests` Bloco M through `MepZipExtract.h`,
  §3 deferred with a dated note (D8); stale docs, the `CLAUDE.md` Author rule,
  line citations → target names, `build_app_macos.sh` versioned, empty
  `Core/SNES|PCE|WS` deleted (D9–D12); MEI v1.3 `pack_id`/`content_id`/`votes`
  + the ADR-0148 rule-1 classify refusal confirmed offline (D13).
- **I.0–I.3 — host input tester** (2026-08-29): gamepad info/state/rumble on
  `IKeyManager` for all three backends; Settings → Input → Test tab with live
  buttons/axes, deadzone ring, drift warning, circularity score and a
  per-device (VID:PID) deadzone; the mapping window highlights the pressed
  button. XAML halves asserted by `UI.HeadlessTests` (ADR-0150, 2026-09-03);
  the physical-pad pass stays hardware-gated.
- **Phase 7 — player shell, P.0–P.7** (ADR-0139/0140/0141, 2026-08-28 →
  2026-09-01): `content_id`/`pack_id` identity, one catalog slot per pack,
  per-ROM preference resolver + Advanced picker, `UiMode` default rule with
  Player chrome/overlay/Esc precedence, pack picker + current-pack chip +
  apply toast, §3.6 catalog update trigger wired into F6.4b, Enhancements
  quick-toggle panel + welcome/Continue cards; GUI wiring asserted by
  `UI.HeadlessTests` (ADR-0150). Normative text in Part B. The on-window
  letterbox fit was closed 2026-09-05 (`0f8535c4`: `UI/Logic/RendererViewportFit`,
  14 `UI.Tests` + 3 `UI.HeadlessTests/RendererLetterboxTests.cs`).
- **Phase 8 — border layer, F8.1–F8.3** (ADR-0149, 2026-09-02): MEP v1.5
  `border` section (`border.png` + `border.json`), VideoRenderer compositing,
  `EnableBorder` toggle, `mep_lint`/`validate-specs` gates, host-free
  `BorderLayout` + Bloco H. Divergences recorded in the spec for an optional
  F8.4: `scale_mode` unapplied, `width`/`height` ignored, 4:3 default, no
  letterbox inside the viewport, bare root `border.png` not linted.
- **Phase 9 F9.0–F9.4 — artist-legible texture sheets** (ADR-0153, accepted
  and amended 2026-09-05): five host-free modules under `Core/NES/HdPacks/`
  (`TileSheetTypes.h`, `MetatileVocabulary`, `ScreenStitcher`, `SheetGrouping`,
  `SheetRender`); F5.4e's union-find retired; `mep_build.py` slices painted
  sheets back with painted-cell precedence; Bloco P. Also fixed the headless
  `input=` no-op (no controller in port 1). Library runs 2026-09-05: 30/30
  packs written; recordings are not deterministic between runs, so only the
  vocabulary artifacts (`metatiles`, `font`, `hud`, `obj000`) compare
  before/after — never a pack diff. Panel spot checks: map recognizability
  passes on Metroid, SMB 1-1 and Excitebike (8224 px track, no duplicated
  loop); cold-read passes at the top of each sheet; the two Zeldas need a GUI
  save state to get past name registration. ADR-0155 (`-MMD -MP`) came out
  of a stale-object segfault met on the way.
- **Phase 9 scrutiny against a Punch-Out!! HD mockup** (2026-09-05): grouping
  already isolates Glass Joe and both Little Mac views; five blockers became
  F9.5/F9.7/F9.8/F9.9/F9.10.
- **F9.5 — sprite (OAM) grouping** (2026-09-05): `SpriteGrouping.{h,cpp}`,
  `sheets/sprNNN.png`; one dominant offset per ordered OAM pair, denominator
  = appearances of A; Excitebike's bike + rider one figure across 25 pose
  groups.
- **F9.6 — optional AI repaint, external** (ADR-0154 accepted, ADR-0161
  `proposed`, 2026-09-05): `scripts/sheet_repaint.py` behind a `RepaintBackend`
  seam (`passthrough`, `classical`, `esrgan`, `diffusion`; availability probed
  before any write; non-loopback endpoints refused), output in
  `auto/repaint/`, MEP-v1 v1.6 `generated` object as disclosure, not a gate;
  `--target screens` run on the real Mega Man 3 recording. Not done:
  validation test 8 (blind A/B) — blocked on a local diffusion stack, not on
  reviewers.
- **F9.7 + F9.11 — alias pass, ink budget** (2026-09-05):
  `MesenSheets::CollapseAliases`, sidecar `aliases[]`, `mep_build.py` fan-out;
  budget = share of the ink of the richer cell (the area rule let one blank
  cell absorb 335 of Ninja Gaiden's 465 entries). Library 10165 → 8684 cells.
- **F9.8 — adjacency evidence before stitching** (2026-09-05):
  `kStitchBandMatch` 0.60 / `kStitchBandLead` 0.25 over cells the anchor
  already carried; single-screen components dropped; Punch-Out!!'s collages
  gone.
- **F9.9 — static screens routed to `<background>`** (ADR-0156, 2026-09-05):
  a screen-resident cell leaves `metatiles.png`; three floors withhold routing
  (not gameplay per F9.13, > `kMaxRoutedSceneShare` 0.93, < `kMinSceneSheetCells`
  30). Punch-Out!! routes 41 % of its scene cells, SMB 8 %.
- **F9.10 — CHR-order layer relegated to `textures/chr/`** (ADR-0160,
  2026-09-05): the `<img>` line carries the path, older packs still load,
  `PruneLegacyChrFiles` sweeps orphaned top-level fragments after a re-record.
- **F9.12 — a continuous region ends when the world is replaced** (2026-09-05,
  amends ADR-0153 §6): still-score cut at `kStitchWorldAgree` 0.85; SMB's
  title no longer baked into 1-1; Excitebike's track 8224 → 15424 px.
- **F9.13 — `scripts/gameplay_probe.py`** (2026-09-05): did the recording
  reach gameplay, answered from the pack on disk; calibrated over 91 packs
  (TP 17 / FN 3 / FP 0 / TN 66); `MENU` is trustworthy, `OK` means nothing
  caught it; wired into `sheet_report.py` and `bootstrap_auto_packs.sh`.
- **F9.14 — headless input in emulated frames** (ADR-0157 amended,
  2026-09-05): `HeadlessInputProvider` resolves an absolute-frame script in
  `SetInput` and pauses on the target frame; power-on RAM zeroed; two runs of
  the same ROM/script yield a byte-identical `auto/` tree under a 20× speed
  spread.
- **F9.15 — in-memory frame capture** (2026-09-05): `BaseVideoFilter::
  CopyOutputBuffer` + `CaptureScreenshot`, host-free `FrameCapture.{h,cpp}`
  (size validation, border bands, FNV-1a checksum), `headless_record capture`
  flag, Bloco S; extended by ADR-0167 (2026-09-07) with a HUD-only capture
  whose `blank` bit is the toast oracle.
- **F9.16 — `sprites.png` sprite vocabulary sheet** (2026-09-07): the full OAM
  vocabulary through the alias pass, `kind: "sprites"` at precedence 1;
  amends ADR-0153 §2–§4.
- **F9.17 — `sheets/adjacency.json`** (ADR-0164, 2026-09-07): complete
  background E/S edge map with degrees and `tiles[]`, sprite `floors[]` bands
  and per-pair `coFrames` next to the pruned offset histogram; the data the
  composition editor (F9.18) builds against. ADR-0166 (2026-09-07) adds per
  screen-resident node the owning `screenNNN` and its offset.
- **Live recorder + viewer** (ADR-0169, 2026-09-08): `LiveFrameRecorder`
  publishes `frame.ppm` / `sprites.json` / `chr.bin` / `nametables.bin` /
  `status.json` by file swap; `scripts/record_viewer.py` is spawned by the
  emulator (Tools → Live Recorder) and never blocks the run; slot re-targets
  per ROM.
- **S10.c/S10.d — pack-side spikes of Phase 10** (2026-09-09): `mep_build.py
  pack` carries the root `generated` disclosure across a rebuild instead of
  dropping it, and an exact-namelist test pins that the zip still ships every
  file under the folder — excluding a `studio/` subfolder is policy no spec
  states, so studio data lives outside the pack folder rather than being
  filtered by the builder. `mep_build.py check-coverage` is the "nothing
  broken" gate for a repainted pack: every baseline tile key still resolves
  and the F5.4d tiles-with-art count over those keys is unchanged, pixels
  never compared. Five `test_mep_build.py` cases, one per behavior, negative
  arm defect-probed. Adjacent bug left unfixed and filed: `pack` drops the
  root `id`, moving catalog identity (#168).
- **S10.a — pose separability measured, and it fails** (2026-09-09): the
  ADR-0168 `evidence[]` walk recovers 6.7 % (Mega Man 3) and 10.5 % (Contra)
  of a main character's poses as distinct figures against a >= 80 %
  criterion, with 0/15 resp. 3/57 poses fitting inside one `sprNNN` group;
  measured on fresh 300 s recordings against poses read off ADR-0169's live
  OAM channel, decode validated at 98.7 % / 94.4 % against the pack's own
  vocabulary. The binding cause is under-grouping, not ADR-0168 §3's
  cross-pose stacking. ADR-0168 amended in place with the numbers and the
  corrected mechanism (still `proposed`); ADR-0170 written `proposed` for the
  prerequisite — a pose sidecar written from `HdPackBuilder::_oamFrames`,
  which the recorder already holds at save time.
- **F9.19 — the pose sidecar** (2026-09-11): ADR-0170 accepted by the user
  and implemented the same day, as Phase 9 debt rather than as a Phase 10
  prerequisite — the F9.18 sprite layer composed fragments, which is the
  defect the human panel would have reported. `BuildPoses` in host-free
  `SpriteGrouping` segments each retained OAM frame into spatially connected
  clusters (within 8 px on both axes, `SheetGrouping`'s DSU promoted to its
  header rather than copied), normalises each to its own top-left through
  the existing round-to-nearest-cell rule, and merges equal sets; the
  recorder writes `textures/sheets/poses.json` next to `adjacency.json` from
  the same pass and the same sprite vocabulary, and reports found / over the
  threshold / kept after the cap. No capture change, no new key, so nothing
  here can break rendering. 27 `core_unit_tests` cases (Bloco P), both arms
  defect-probed — the 8 px boundary is asserted against the literal, not
  against its own constant, after the first probe showed a drifting
  `kPoseMaxGap` passing unnoticed. Consumer side (ADR-0170 §4): the
  composition engine takes a figure's layout from the sidecar when the pack
  has one and otherwise runs the ADR-0168 walk unchanged, proven by a spy
  rather than inferred from output; a malformed or partial sidecar degrades
  to the fallback instead of raising. Three implementation semantics the
  tests forced into the open (the frame floor counts `RepeatCount`, "found"
  is already past the tile floor, "kept" is pre-cap) are recorded in
  ADR-0170 §2. Open, and deliberately not invented: which poses belong to
  the same subject — ADR-0170 declines it, so a figure is still identified
  by its anchor node.
- **S10.a re-measured, and it passes** (2026-09-11): a fresh 300 s Mega Man 3
  recording on the F9.19 binary, ground truth read the same way as the
  failing run (ADR-0169's live OAM channel, 1 369 captures, canon keying),
  puts **25 of 25** of the main character's poses in the pack's
  `poses.json` — 100 % against the >= 80 % criterion, from 6.7 % on
  2026-09-09 — and 68 of 72 (94.4 %) of every ground-truth pose. The
  agreement is a cross-implementation check rather than a tautology: the
  file is C++ over the retained, de-duplicated `_oamFrames` stream keyed by
  vocabulary node, the ground truth is Python over the live channel keyed by
  canonical CHR bytes. The reverse ratio is low by construction (68 of 223
  file poses appear in the ground truth) because the live channel publishes
  one capture every 50 frames and so never sees most of what the retained
  stream holds. The first measuring pass read the node → shape mapping off
  `sprites.json` and scored 76 %; that was the measurement, not the file —
  the sheet draws only the 241 cells it routed while `poses.json` indexes
  all 288 vocabulary nodes, so a third of the file was being discarded.
  `adjacency.json` `sprites.nodes[]` is the authoritative mapping. Evidence:
  `runs/s10a-rerun/S10a-rerun-summary.json` (untracked, like the first run's).
- **F9.18 sprite layer: the pose becomes its unit** (2026-09-11): ADR-0171
  accepted by the user and implemented the same day, superseding ADR-0168.
  The editor seeds, ranks, locks, previews and exports **poses** read from
  F9.19's sidecar; the ADR-0168 `evidence[]` walk stays as the fallback for
  a pack recorded before ADR-0170, and the bare node as the degenerate case.
  Engine: `pose_anchor` (rarest member, so a character's poses do not all
  resolve to one silhouette on reopen), `pose_bottom_nodes` /
  `pose_band_members` (ADR-0171 §3 band = bottom row), `pose_rank`
  (`sum(coFrames)/sqrt(members)`, §4), `pose_art`, `pose_cells`; the View
  draws silhouettes in variable-sized row cells over a host-free
  `compose_editor_layout.row_metrics`, where `cell_origin`/`index_at` stay
  exact inverses and `metrics=None` reproduces the old fixed grid to the
  pixel. `export` is unchanged in format (§5): `seed`/`locked` still name
  nodes, one anchor simply writes a whole silhouette's cells. 34 headless
  cases across the engine, ViewModel and GUI suites (23/23, 11/11, 56/56),
  six defect probes (rarest → most common anchor, sqrt → mean, art-less
  member exported, band = any member, and the two dedup rules) each failing
  at least one case. Judged by render-to-PNG against the ADR-0170-era pack
  `runs/s10a-rerun/work/MegaMan3/auto`: the composed band draws whole,
  recognisable enemies instead of slivers.
  Three defects the real pack exposed and the synthetic fixture could not:
  `pose_cells` emitted members no sheet draws, which made a pose whose
  vocabulary node was never routed impossible to export at all (the same
  288-vs-241 mismatch that cost the first S10.a pass 24 points); the
  candidate list offered a silhouette already composed, because several
  anchors resolve to one pose, and the seed palette listed the same
  silhouette under two anchors; the export caption counted locked anchors
  (4) instead of the cells the file carries (19).
  Known and accepted, for the human panel to weigh: only **62 of 223** poses
  on that pack are addressable, since `pose_of(anchor)` resolves to the
  most-seen pose containing the anchor and ADR-0171 §5 deliberately adds no
  field to name a pose; and the export preview shows the later poses with
  holes, because a node already placed is not emitted twice (§5, `mep_build`
  fans a painted cell out by tile key).

- **The rebuilt pack matches again on a CHR ROM game** (2026-09-12): ADR-0172
  accepted by the user and implemented the same day. A `hires.txt` key is two
  different things — 32 hex of tile data on a CHR RAM game, a CHR index on a
  CHR ROM one — and the ADR-0153 sidecar recorded only the data, so
  `mep_build.py build` emitted the CHR RAM form for a CHR ROM game and the
  rebuilt pack matched **0** tiles at run time while still loading and still
  drawing its `<background>` captures. Measured on a fresh Mega Man 3 pack
  over a 100 s headless run, reading `[HDPack-Debug] bg tile match rate`: the
  bootstrap's own pack 100 %, the rebuild before the ADR 0 of 3 455 861 /
  3 390 239 / 3 192 008, the rebuild with it 479 861 / 295 199 / 450 368 of
  the same three. `SheetTileKey` gains `TileIndex` **outside** its identity —
  `operator==`, `operator<` and the hash still compare `TileData` +
  `PaletteColors`, so vocabulary, dedup and every grouping decision are
  bit-for-bit unchanged — filled from `HdBuilderPpu`'s absolute
  `AbsoluteTileAddr / 16` (no bank id: the value is already absolute across
  the whole CHR ROM). A sidecar tile entry gains an optional `"index"`;
  `mep_build.py build` emits the index form only when the key source's own
  `<tile>` lines are index-keyed **and** the entry carries one, and otherwise
  **fails** with a named error rather than shipping a pack that renders
  nothing. A pack recorded before this ADR is therefore not silently
  degraded, it is refused. Issue #170.
- **A sprite that never moved stops poisoning the band it is painted in**
  (2026-09-12): ADR-0173 accepted by the user and implemented the same day,
  amending ADR-0164 §1. `floors[]` answers "who stands on this ground", but a
  HUD bar stands on nothing — it is painted in several stacked rows every
  frame, so it joined seven bands at once on Mega Man 3 and, being the
  most-seen shape in the capture, headed each one's suggestion list. The
  signal was measured before the threshold was chosen: over a 120 s scripted
  capture (4096 OAM frames, 288 nodes), frames-per-distinct-position runs
  609.0 / 253.3 / 139.6 for the three HUD nodes against a **median of 4.3**.
  The first attempt used `appearances` as the denominator, which multi-counts
  instances within a frame and is biased; `NodeFrames` (once per frame) is
  what the file now carries, next to `Positions`. The recorder classifies and
  labels — `screenFixed` when `frames >= 64` and `positions * 32 <= frames` —
  and `compose_engine` filters; `floors[]` is still written for a
  screen-fixed node, and nothing is deleted, so a reader that disagrees has
  the verdict and the two numbers behind it. 30 of 288 nodes classified, 19
  of 30 bands shed 1–11 false members. Known trade: an actor that genuinely
  never moved during a capture is misread as furniture. Issue #167.
- **Four smaller defects from the same pass** (2026-09-12): `mep_build.py
  pack` and `mep_recipe._write_pack_json` both dropped a pack's declared
  `id` on a re-pack, silently demoting its ADR-0140 identity from source (1)
  to a weaker one — the second site was an undiscovered mirror of the first
  (#168); the composition editor exported at 1x instead of the pack's scale
  and carried unreadable chrome (#169, #171). All five issues (#167–#171)
  are closed and Done on the board.

- **The panel ran its own sections 2 and 3, and produced four defects**
  (2026-09-12): the first pass on a pack that actually applies, by two
  evaluators given no access to the code or the ADRs. Both sections **failed**,
  and both verdicts held up under re-measurement, though neither report was
  right as written — a cold evaluator errs in both directions, and every
  headline was re-derived before it became an issue.
  - **#174** (fixed, ADR-0174): 35 sprite pairs at `count == coFrames == 1338`
    at one constant offset — nodes never once on screen apart — split across
    `spr###` sheets. A `sprNNN` sidecar now names the `poses.json` ids its
    cells belong to, ordered most-covered first. The join rather than a
    grouping change, because grouping changes invalidate every recorded pack:
    verified by re-recording Contra, where all 130 sheet PNGs and `poses.json`
    come back byte-identical and every sidecar matches once the new keys are
    removed. `spr018` and `spr023` both name `pose001`, which covers 9 of the
    9 nodes of the two combined.
  - **#175** (half fixed, ADR-0175; half withdrawn): a group sheet states its
    blank slots instead of filling them — the grid is the bounding box of a
    BFS layout, so a non-rectangular figure holes by construction, and filling
    would put two crops under one tile key, which the rebuild silently
    collapses. The report's second half was wrong: the 14 background nodes on
    no sheet are screen-resident, and 14 of 14 resolve to an existing
    `backgrounds/screenNNN.orig.png` through ADR-0166's `screens[]`. Its
    original count, 37, was wrong too — it did not follow `aliases`.
  - **#172** (fixed): `check-coverage` never said which layout it expected,
    advised `run build first` when `build` had run, and let a baseline that
    `build` had overwritten be compared against itself. The issue's own
    diagnosis — two incompatible layouts — was wrong; `cmd_build` reads both
    shapes under one rule. The fix is the messages plus a `samefile` refusal.
  - **#173** (fixed): `build` announced 644 surviving keys of 10057 as good
    news. It now reports a key-by-key delta (which surfaces the 1 key the
    sheets *add*, invisible to a subtraction), states that dropping keys is
    expected under ADR-0043/0156/0160 and points the artist at
    `backgrounds/screenNNN.png`, and groups the 76 warnings about the
    recorder's own sheet geometry instead of burying the actionable lines.
  - **Still open, deliberately**: `spr016` renders `GA M` / `OV R` because its
    `E` is in *zero* slots, not because a repeat was de-duplicated. The glyph
    occurs twice per frame, so its ADR-0153 §2 `appearances` denominator is
    double every partner's and every edge from it is dropped — **a tile that
    repeats within one frame can never join a group.** Same biased-denominator
    shape as ADR-0173, and it wants the same treatment: measure the
    distribution before choosing the rule.
  - Section 2's pass criterion was amended the same day (§5, Phase 9
    validation): it judged sheet cells, which ADR-0171 had already stopped
    being the unit, and was unpassable by construction.
  - **#179** (fixed, ADR-0177): found while assembling the bench for the
    human run of section 2. `BuildPoses` clusters a frame by spatial
    connectivity, so any two actors that touch fuse into one entry, and the
    pose list repeats the same figure with a different bystander each time —
    the mirror of the split-cell defect the criterion amendment addressed,
    with the unit arriving too large instead of too small. An entry is now
    labelled `fusionOf` when its tiles split, at some translation, into two
    entries the recorder also saw standing alone; the editor stops offering
    a labelled entry, in the band list and when laying a figure out. No
    threshold: the classification is a property of the tile sets. A
    frequency ratio was measured first and rejected — continuous from 0.0 to
    562 across the kit, with no plateau, and backwards on Excitebike.
    Re-recording the kit labels 44 of 223 Mega Man 3 poses, 39 of 84
    Zelda 1, 21 of 85 Contra, 12 of 77 Excitebike; each pack's `poses.json`
    comes back identical apart from the new field, and the only other files
    that change are the 52 `sprNNN` sidecars whose ADR-0174 `poses[]` list
    stops citing a fusion.
  Logs: `runs/golden-20260912/panel-section2.md`, `panel-section3.md` (not
  versioned). The golden kit was re-recorded on the ADR-0172/0173 binary the
  same day: Mega Man 3 and Excitebike carry tile indices (CHR ROM, 1037 and
  392), Contra and Zelda 1 correctly carry none (CHR RAM); Excitebike's
  rebuilt pack was measured back at 100 % `bg tile match rate`, the first
  independent confirmation of ADR-0172 outside Mega Man 3.

### 4. Roadmap — pending work, by slice

#### Phase 6 — Community pack auto-install (MEP Recipe v1)

**Shipped** — F6.0–F6.8, 2026-08-28 → 2026-09-04 (ADR-0138, 0143, 0144,
0146, 0148, 0151, 0152); record in §3. It realized the former Phase 4 (pack
browser + official index): the catalog JSON is the MEI, the Issue Form is the
contribution path, install/update happens in the client.

| Pending | State |
|---|---|
| F6.5 native OS file-picker step of the user-supplied-audio install | manual; no live row can raise the prompt today (all rows `hd-legacy`); every other step of that pass is unit-tested |
| CI live validation (`LIVE_VALIDATION_ENABLED` → `'true'`, also arms the autofix-PR step) | deferred by user decision 2026-08-29 |

Non-goals (unchanged): hosting or committing third-party content; scraping
Google Drive/MEGA confirm flows (the user supplies those files); fabricating
missing assets; adjudicating patch licenses. Edge cases the pipeline must
keep handling, all covered by `mep_lint.py`: nested zip-in-zip, whole-repo
archive wrapper, bare root, named subfolder ≠ ROM, several `hires.txt` after
acceptance (fail closed, list candidates), Google Drive large-file
interstitial (out of automatic scope).

#### Phase 5 — bootstrap

**Shipped** — F5.1–F5.5, 2026-08-25 → 2026-08-29; record in §3. Success
criterion unchanged: *playing for 5 minutes generates, next to the ROM, an
enhanced game (image level 2, sound level 2/3) with no configuration; from
it an artist reaches a publishable pack in < 1 h editing only PNG/OGG*.
Phase 9's validation protocol is where that criterion is now measured.

Pending: the audible end-to-end of Blocks B–D (real game, real ears —
subjective, stays manual); the bundled SoundFont waits on the installer's
first release.

#### Repo hygiene and tests

**Shipped or closed** — H1–H10; record in §3. Open: ADR-0162 (accuracy
suite) is `proposed` and not in CI by decision; the `CheatTypeDetector`
GB/SMS product decision (H7) stays deferred.

#### Documentation and normative integrity

**Shipped** — D1–D13, audit of 2026-09-01; record in §3. Open: ADR-0120 §3
(optional ROM-name parameter in `MepZipValidator`), deferred with a dated
note in the ADR — pick it up with a per-ROM install caller.

#### Host input tester (host UX, not a pack feature)

**Shipped** — I.0–I.3, 2026-08-29; record in §3. Pending, hardware-gated:
the physical-pad pass (live highlight, ring, rumble), MBC7/GBA tilt UI,
Linux `UpdateDevices()`, macOS pads without `extendedGamepad`. Out: preset
redesign, HUD overlay, special devices (Zapper, Power Pad, Phaser),
automatic remapping, browser Gamepad API, stats collection.

#### Deferred / optional

- OGG replacement audio on GB/SMS (`hires-gbsms-v1-draft`) — frozen until a
  second implementer exists (ADR-0041).
- ML-model upscale as an alternative to xBRZ in `scripts/` — later.
- Automatic IPS relocation across ROM revisions — no.
- Offline AI tools (ESRGAN batch upscale, LLM-assisted preset tuning) —
  optional external tools on top of the bootstrap, never in the emulator.
  The LLM-assisted *skin* tool is under feasibility spikes in Phase 10 and
  returns here if they fail.
- Pack browser UI beyond auto-install (search, ranking by GitHub signals,
  user-configurable extra MEI URLs with explicit confirmation, MEI §3.4) —
  after Phase 6, if the catalog grows past what a list can show. The
  player-shell picker (one ROM, 2+ `pack_id`s) is **not** that browser;
  it lives in Part B §5.

#### Phase 7 — Player shell (minimal GUI)

**Shipped** — P.0–P.7, 2026-08-28 → 2026-09-01; record in §3, normative
text and slice list in Part B (do not duplicate that prose here). Pack
identity is the pair `pack_id` (product) + `content_id` (revision); the
catalog keeps one live slot per `pack_id`. The letterbox fit, once the last
manual item, was closed 2026-09-05 (`0f8535c4`); the only manual residue is
the native file picker (F6.5).

#### Phase 8 — Enhancement pack border layer

**Shipped** — F8.1–F8.3, ADR-0149, 2026-09-02; record in §3. Optional and
unscheduled **F8.4**: apply `scale_mode`, honor the console aspect in the
default viewport, letterbox inside the viewport, lint the bare root
`border.png`. Core/pack-format work, so it stays in Part A.

#### Phase 9 — Artist-legible texture sheets (bootstrap output redesign)

**Status.** F9.0–F9.17 shipped 2026-09-05 → 2026-09-07 (record in §3);
F9.18 in delivery — code and GUI acceptance are done, the human panel is
not. Two proxy passes ran on 2026-09-12, both by evaluators with no access
to the code: the first reached only its cold-read section, because the pack
it judged matched 0 % of its background tiles (ADR-0172); the second, on the
golden kit re-recorded that day (`runs/golden-20260912/`, not versioned),
ran sections 2 and 3 and failed both, yielding #172–#175 and ADR-0174/0175
(record in §3). Section 2's criterion was amended in the same pass. What is
still owed is the panel itself — a person, not a proxy; an agent that wrote
the feature cannot be the artist who has never seen it, and both passes are
labelled proxies for that reason. The problem statement below is kept as the
baseline the validation protocol measures against.

**Problem.** The bootstrap `auto/` pack emits `Chr_N.png` sheets in CHR
order: thousands of 8×8 fragments with no neighbourhood — half a logo,
one corner of a rock, a run of font glyphs. An artist opening `mep/` of a
hand-made pack (Zelda 1 reference) sees whole bushes, trees, a stitched
overworld; opening `auto/` sees noise. F5.4e was meant to bridge this
(objects from spatial co-occurrence) but its global union-find over
"≥2 sightings" edges collapses any contiguous scene into one component,
so `textures/sheets/object*.png` was **never** emitted on real games.
Spike 2026-09-04 (`scripts/spike_tile_sheets.py`, env-gated grid dump in
`HdPackBuilder::OnFrameEnd`, evidence under `runs/spike-sheets/`, not
versioned): Zelda 1 — 59/59 shapes in one component (F5.4e), versus 62
aligned 16×16 metatiles (bush, tree, rock, sand, forest edge) and 5
screens stitched into one map with the metatile/PMI approach; Excitebike —
132/132 in one component, versus a 23 712 px continuous strip with ramps.

**Goal.** The bootstrap writes, next to the ROM, sheets an artist can read
cold and paint over: a **metatile vocabulary** (one cell per in-game
building block, aligned to the game's grid), **stitched maps** (screens
assembled as the player sees them) and **object sheets** (multi-block
figures that always appear together), each round-tripping through
`mep_build.py` back into `hires.txt`. Success criterion is Phase 5's
("publishable pack in < 1 h editing only PNG/OGG") made concrete by the
validation protocol below.

**Principles.**
- Presentation is for humans: transparent background, 1-cell gutters,
  labels in a sidecar JSON (never baked into the PNG), sheets split by
  context (HUD / font / scene) so a rupee counter never sits between two
  trees.
- Grouping is by **mutual predictability**, not raw counts: A and B join
  when P(B east of A) and P(A west of B) both clear a threshold with a
  minimum count — sand next to everything is not an object; a 2×2 boss
  door is.
- The unit is the game's grid: 16×16 aligned to the attribute grid when
  the game uses one, 8×8 only when the recording is too thin in aligned
  placements to justify 16. Detection is automatic and reported; the artist
  never picks. *Measured 2026-09-05: both golden games select unit 16 — the
  spike's "Excitebike falls back to 8×8" claim did not survive the amended
  criterion; what separates them is `hasGrid` (Zelda 0.34, Excitebike 0.03).*
- Nothing inferred can break rendering (F5.4e rule kept): sheets add art
  for tiles already keyed by `hires.txt`; wrong grouping only costs
  legibility, never a missing tile.
- Vanilla-looking output stays in `auto/`; community art is never masked
  (ADR-0049/0050/0147).

**Non-goals.** A tile-map editor; a game-specific level format; changing
`hires.txt` semantics (MEP textures stay an envelope over HD Pack per
ADR-0005); AI generation inside the emulator (stays an external script —
F9.6 and Phase 10).

| Slice | Deliverable | Decision |
|---|---|---|
| F9.18 | **The composition editor** — an external, stdlib-only Python tool in `scripts/` (`scripts/compose_editor.py <pack folder>`, a tkinter layered canvas over a host-free `compose_engine.py`) that opens a pack recorded since F9.17 and builds the ADR-0164 §5 scene as a stack of layers: HUD/font edited in place, background from maps/metatiles/screens, objects from `objNNN`, and sprites as one sub-layer per **Y band** — `adjacency.json` `sprites.nodes[].floors[]` joined with `pairs[].coFrames`, ranked by `coFrames × band overlap`. Seed → rank → lock → recompute runs inside a layer, placing a candidate's `sprNNN` figure by the near-field `offsets[]` when one exists; export is in-place sheets for HUD/background/objects and a `usrNNN` sidecar (`composed: true`, `seed`/`locked`, `band {bottom, tolerance: 8}`) per kept sprite band. Node pixels come from the sheet that shows them (`*.orig.png`, nearest-neighbour); a screen-owned node (ADR-0156) from `backgrounds/screenNNN.orig.png` or a `textures/chr/` render, never a silent blank. No new format: the output is ordinary `mep_build.py` input (`_SHEET_RANK` ranks by `kind`; `usrNNN` sorts after `objNNN`/`sprNNN`); unpainted scenes live under `auto/`, a painted sheet is written to `mep/` (ADR-0147). The two ADR-0164 acceptance tests (seed on a Ninja Gaiden `obj000` metatile → rest of the group ranks first; the Y band of Ryu's bottom edge ranks ground enemies above projectiles) are suites against the engine, headless | **accepted 2026-09-07** — ADR-0165 (accepted 2026-09-07, by the user); delivery in progress. ADR-0166 (accepted 2026-09-07) closes the F9.18 pixel-source gap: `adjacency.json` records, per screen-resident node, the `screenNNN` that owns it and its 8 px on-screen offset, so a sheetless background cell resolves to a crop from `backgrounds/<screen>.orig.png`. **Engine acceptance run against real data, 2026-09-07** (`runs/f918-accept/report.txt`): a fresh 300 s Mega Man 3 recording since F9.17 (62 sheets, `vocabularySize` 379, 15 distinct screens, 77 background nodes carrying `screens[]`) exercised `background_rank`/`sprite_rank`/`node_art`/`export` end to end — a screen-owned node's crop is real, legible pixels (spot-checked visually, not just "did not raise"), and both a `usrNNN` object and sprite-band export round-trip through `mep_build._load_sheet_docs` unchanged. Found and fixed a real bug no synthetic fixture caught: `Pack.next_free_name()` scanned the pack's own `sheets_dir` instead of the caller's `to_dir`, so two exports into the same `mep/` folder — an ordinary editing session — both landed on `usr000` and the second silently overwrote the first on disk; fixed, with a defect-probed regression test (`test_export_twice_to_same_dir_gets_distinct_names`, 9/10 → 10/10). Engine code acceptance is done. **GUI pass 2026-09-09:** `scripts/render_compose_editor.py` opens the real `EditorApp`, drives its handlers by named step and repaints the mapped widget tree into a PNG (the `render_record_viewer.py` technique of ADR-0169 — no screencapture, no TCC prompt), so the GUI needs no display to be judged either. It exposed a headline defect the engine tests could not see: `_refresh_row` drew cells column-major while `_row_index_at` hit-tested row-major, so every cell after the seed was drawn below the canvas and clicks landed on the wrong cell — the whole lock/swap/remove gesture set was unusable. Fixed by moving the grid arithmetic into host-free `compose_editor_layout.py` (ADR-0127) where `cell_origin`/`index_at` are exact inverses, plus five packing/contrast defects (clipped export preview, Selection panel squeezed off the right edge, squeezed tab buttons, clipped Output path, four #aaa/#888 labels on the aqua theme). `scripts/test_compose_editor_gui.py` covers the layout invariants host-free and drives the real app Tk-gated (36/36; the old origin fails 14 checks; no display skips 3 cases with rc=0). Remaining before "shipped": the Phase 9 human panel (cold-read/find-and-edit/seam) and native window-manager behaviour only a desktop shows. Note for that panel: the composed band renders **fragments** of a character, not poses — the correct unit is what PRD Phase 10 spike S10.a measured as unreachable from today's sidecars, so a "still striped" verdict would be ADR-0170's subject, not a GUI defect. **Resolved 2026-09-11:** ADR-0171 (accepted, supersedes ADR-0168) makes the pose the unit of the sprite layer, and the slice shipped the same day (record in §3) — the composed band now draws whole characters, so the human panel judges poses. Run it against a pack recorded since ADR-0170; an older pack measures the fallback, which is the 6.7 % path. **Proxy panel 2026-09-12** (`runs/f918-panel/panel-log.md`, not versioned): run by a session that had not built the editor, against a rebuilt Mega Man 3 pack — and it invalidated its own sections 2 and 3. The pack under test matched **0 %** of its background tiles at run time (ADR-0172, #170), so "the edit reaches the screen" was never actually observed; the magenta the log called proof was the game's own palette. Sections 2 and 3 are marked **not reached** and the pass produced five real bugs instead (#167–#171, all closed; records above). The human panel still owes sections 2 and 3, now against a pack re-recorded on the ADR-0172/0173 binary — `runs/golden-20260912/` holds the re-recorded golden kit |
| F9.19 | **The pose sidecar** — `textures/sheets/poses.json`, written at save time next to `adjacency.json` from the same retained `_oamFrames` stream and the same sprite vocabulary: every frame segmented into spatially connected clusters (within `kPoseMaxGap` = 8 px on both axes), each normalised to its own top-left as a set of `(node, dx, dy)` at `SpriteGrouping`'s round-to-nearest-cell rule, equal sets merged and `RepeatCount`-weighted, kept at >= 3 frames / >= 4 tiles and capped at `kMaxPoses`. Host-free `BuildPoses` + `SerializePoses`, I/O only in `HdPackBuilder`; the composition engine reads the sidecar when the pack has one and otherwise runs the ADR-0168 walk unchanged | **accepted 2026-09-07 / 2026-09-11** — ADR-0170; **shipped 2026-09-11** (record in §3). The prerequisite S10.a named: the ADR-0168 `evidence[]` walk recovers 6.7 % of a character's poses because the pairwise projection cannot be inverted, and the datum was never missing from the emulator, only from what it wrote down |

**Validation — qualitative and intuitive.** The deliverable is legibility,
which no pixel metric captures, so each slice is judged by a fixed panel
of tasks run by a person who did **not** build the feature (the artist
persona — a developer may stand in but must not have seen the sheets
before). Golden games: Zelda 1 (16×16 grid, screen scrolling), Excitebike
(no grid, continuous scrolling), Mega Man 3 (CHR ROM), Contra (CHR RAM);
GB/SMS follow once NES passes. Each run records the `auto/` folder, the
answers and elapsed times as a short `runs/` log (not versioned) and one
summary line in this PRD's shipped record.

1. **Cold-read test** (F9.1, F9.3, F9.5). Open `sheets/*.png` for the first
   time, 60 s per sheet, name aloud what each cell is. Pass: ≥ 80 % of
   scene metatiles / objects named correctly ("bush", "tree", "Link"); HUD
   and font sheets recognised as such at a glance; no cell described as
   "half of something".
2. **Side-by-side with the artist pack** (F9.1–F9.3). A golden game's
   `auto/` sheets next to a community `mep/` pack's: every subject the
   artist drew as one figure is **addressable as one unit** in `auto/`.
   Pass: no subject the artist treated as a unit is unreachable as a unit
   in ours; list the exceptions.

   **The unit is the pose, not the sheet cell** (amended 2026-09-12, on
   ADR-0171, which made the pose the unit of the sprite layer and the
   `sprNNN` figure the fallback). The criterion as first written judged
   sheet cells, and by 2026-09-12 it had become impossible to pass by
   construction: the grouper deliberately cuts a shared sub-figure out to
   its own sheet — a pair of legs worn by two torsos is stored once — so a
   whole character is *always* split across `sprNNN` cells, on every pack,
   for a reason the architecture is not going to give up. A sprite subject
   therefore passes when one `poses.json` entry covers it, reachable from
   the sheets through ADR-0174's `poses[]`; a background subject still
   passes on the cell/object surface, where nothing forces a split, and a
   screen-resident cell passes on its `backgrounds/screenNNN.png`
   (ADR-0156, ADR-0166) — a captured screen **is** a painting surface, and
   the 2026-09-12 audit failed to count it as one.

   Zelda 1 was the nominated game and is not usable: its artist pack is
   distributed only via Google Drive, which this project does not fetch
   (Phase 6 non-goals). Contra is the substitute — the artist pack is on
   an allow-listed host.
3. **Find-and-edit test** (F9.4). Task card: "make every bush purple",
   "put a face on the rock", "draw a road marking on the ramp". From
   opening the folder to seeing the change in the emulator: pass when
   < 10 min with no editor other than an image editor and
   `mep_build.py`, and the person never had to open `hires.txt`.
4. **Seam test** (F9.2, F9.4). Paint a continuous diagonal stripe and a
   checkerboard across `map-NNN.png`, rebuild, play the stitched region.
   Pass: the stripe is continuous across every metatile boundary and
   every screen transition; no doubled or missing column at the seams
   (headless screenshots along the route, eyeballed, plus a diff against
   the untouched-sheet run to prove only the paint changed).
5. **Map recognizability** (F9.2). Show `map-NNN.png` alone. Pass: the
   person points to where the game starts and traces the route they
   would take; for Excitebike, identifies the ramps and the finish line.
6. **Nothing-lost test** (all). Identity round-trip renders every
   captured screen pixel-exactly (automated, `headless_record`), and the
   F5.4d coverage line reports the same tiles-with-art count before and
   after the redesign for a 5-min play.
7. **Noise budget** (F9.1, F9.3). Count cells with count = 1 or flagged
   "unaligned"; pass when they sit in a separate `misc` sheet and make
   up < 15 % of scene cells (Zelda spike: count-1 cells were GAME OVER
   text — correct to isolate, wrong to interleave).
8. **AI blind A/B** (F9.6 only). Five screens, artist pack vs AI repaint,
   unlabelled; three reviewers. Pass to keep the slice: the AI output is
   preferred or tied on ≥ 2 of 5 screens **and** fails seam test 4 on
   none; any visible alpha loss on sprites fails the slice regardless.
   **Blocked, and not on a reviewer.** There is no AI repaint to judge yet:
   the `diffusion` backend of `scripts/sheet_repaint.py` has never been
   executed, because ADR-0154 §2 deliberately makes the weights and the
   local ComfyUI/`diffusers` process the user's to install, and this machine
   has neither. Its driver and its unavailable paths are covered; its
   generation path is untested code. The precondition is therefore a local
   stack, not three humans — until someone installs one, the `classical`
   backend is the only non-`passthrough` arm that has produced pixels, and
   this test does not run.

Tests 3, 4 and 6 have automatable halves (rebuild, headless run, diff)
that go into `make doc-checks`/`scripts/test_mep_build.py`; the judgement
calls (1, 2, 5, 7, 8) stay human and are repeated per golden game.

#### Phase 10 — LLM-assisted skin studio (feasibility spikes first)

**Status:** drafted 2026-09-09 as a nine-slice product plan; **rewritten
the same day after review** into the feasibility spikes below. **No work
started.** Nothing in this section is a decision: no module layout, sidecar
format, tool contract, storage location, provider or emulator entry point
is fixed here. **S10.c/S10.d shipped 2026-09-09; S10.a ran the same day and
failed** — its premise ("every pose the recorder saw") is not reachable from
today's sidecars. The user took that decision on 2026-09-11: **ADR-0170 is
accepted and shipped as F9.19** (§3) — the recorder now writes pose
membership — and **S10.a was re-measured the same day and passes at 100 %**
(25 of 25 of a character's poses, against >= 80 %; §3). ADR-0170 was
accepted on its Phase 9 value rather than as a commitment to this phase, and
one link is still unmeasured: **S10.b**, the layout fidelity of a hosted
image model, which needs the user's key and hand. It does not depend on
poses — Contra80s' `BillRizer.png` is already a contact sheet of one
character's poses, and it is public third-party art, so running the spike on
it sends no ROM-derived art anywhere and leaves ADR-0154 §2 untouched. Each of those is an ADR, written by hand after the spike that
tests its premise (`docs/roadmap/AGENTS.md`: decisions are not made in a
PRD). The first draft had it backwards — it specified the architecture and
reserved "ADR-A/B/C" to ratify it; that draft is in git history, not here.

**Problem.** A hand-made restyle is an artist's year. The reference pack,
Contra80s (`tastichacks/contra80s`, `docs/community-packs.json`), is 233
files and a 21 179-line `hires.txt`: 11 854 `<tile>` entries, 864
`<condition>` lines, one PNG per subject — `BillRizer.png` is a 512×432
sheet at `<scale>2` holding every pose of one character. Phase 9 made the
machine's output legible (metatile vocabulary, `sprites.png`, `sprNNN`
figures, stitched maps); F9.18 lets a human *compose* a scene; F9.6
repaints a sheet at a higher resolution but keeps the drawing. None of them
lets a player who cannot draw say "make Bill look like a chrome knight,
keep the gun" and play the result.

**Idea under test.** From the live viewer (ADR-0169) the player points at
a subject, describes a restyle, and an external tool driven by a hosted
image model under the player's own key produces a candidate skin for the
**whole subject** (every pose the recorder saw) that the unchanged
`mep_build.py` slices into a pack. Whether any link of that chain holds is
what the spikes measure.

**Constraints that hold regardless of outcome.**
- Part A §1 principle 5 as written: no model call, key or prompt in
  `Core/`, `UI/` or the installer. If a studio exists it is an external
  script in `scripts/`, like the viewer and the composition editor
  (ADR-0165, ADR-0169).
- ADR-0154 §2 and §4 stand until an ADR amends them: today no tool in this
  repo sends ROM-derived art off the machine (`sheet_repaint.py` refuses a
  non-loopback endpoint), and generated output lands in `auto/`, never
  `mep/`. Sending crops to a hosted model is a decision to take *against*
  that ADR with spike results in hand — not a premise of this phase.
- The model never writes the format. Deterministic code validates every
  byte that reaches a pack; Phase 9's rule — nothing generated can break
  rendering — is kept verbatim.
- Provenance is disclosure, not a gate (ADR-0154 §3, MEP v1.6 `generated`).
- GB/SMS only after NES passes.

**Gaps found in review (2026-09-09) that the spikes must answer.**
1. **Pose membership does not exist in the data.** ADR-0168 (`proposed`)
   says a `sprNNN` group spans several poses, the pack records only
   pairwise tile totals, never which tiles co-occurred in one OAM frame,
   and its layout walk *drops* members rather than separating poses. A
   subject sheet "with every pose" cannot be built from today's sidecars;
   accepting ADR-0168 does not change that. Either the recorder records
   pose membership (a bootstrap change, its own ADR) or the unit is
   smaller than "the character".
2. **Layout fidelity of a hosted image model is unmeasured.** Whether a
   generated image keeps a contact sheet's cells in place, leaves gutters
   clean and returns alpha (assume not — ADR-0154 §7) is unknown.
   Chroma-key plus silhouette intersection is a hypothesis to measure, not
   a rule to specify.
3. **Export leaks local data and drops the label.** `mep_build.py pack`
   zips every file under the folder (`folder.rglob("*")`) and rewrites
   `pack.json` carrying over only `patches`/`crc32`/`md5` — so anything
   stored under `mep/` (transcripts, candidates, egress logs) ships with
   the pack, and a root `generated` object is lost on export. Studio data
   must not live under `mep/`, and `mep_build.py pack` must carry
   `generated` — a fix worth making now, independent of the phase.
4. **There is no reverse channel to the emulator.** ADR-0169 is one-way:
   producers publish, the viewer never sends. "Save state → power-cycle →
   restore" from an external tool is a new interop surface plus an
   ADR-0169 amendment, not "the existing interop".
5. **The identity test does not apply to a painted pack.**
   `scripts/test_mep_build.py`'s identity round-trip is pixel-exact for
   untouched sheets; a skin changes pixels by definition. The "nothing
   broken" check for a generated pack is *key/coverage preservation* —
   every tile the recorder keyed still resolves, F5.4d count unchanged —
   and that test does not exist yet.

**Provider facts (ai.google.dev, read 2026-09-09 — configuration, not
decisions; they churn).** Image models: `gemini-3.1-flash-lite-image` (1K
only), `gemini-3.1-flash-image` (0.5K–4K; $0.067 per 1K image, $0.101 per
2K), `gemini-3-pro-image` (1K/2K $0.134; adds style references),
`gemini-2.5-flash-image` (legacy). Interactions API: key in the
`x-goog-api-key` header, `response_format {type: "image", mime_type,
aspect_ratio, image_size}`, `previous_interaction_id` for multi-turn
(tools, system instruction and generation config are re-sent each turn);
Gemini 3 text models combine function calling (`tool_choice
auto|any|none|validated`) with structured output. Image models have **no
free tier**; paid-tier prompts are not used for product improvement. Every
image carries a SynthID watermark. Keys: new AI Studio keys are
service-account-bound "auth keys"; unrestricted standard keys are already
rejected and **all** standard keys stop working in September 2026. Not
documented anywhere, hence spikes: alpha output, pixel-exact layout
preservation, per-model rate limits.

| Spike | Question | Pass / fail | Feeds |
|---|---|---|---|
| S10.a | **Can poses be separated from a recorded pack?** Run the ADR-0168 walk on fresh Mega Man 3 and Contra recordings; count poses recovered as distinct figures against poses visible in `sprites.png`. If the walk fails, prototype recording OAM co-occurrence per frame in the bootstrap and re-measure | ≥ 80 % of a main character's poses as distinct figures, HUD excluded — else the recorder change is the prerequisite and goes first | ADR-0168 (accept / supersede); a recorder ADR if pose membership is needed — **measured 2026-09-09: FAIL.** Fresh 300 s recordings of both games, poses counted off ADR-0169's live OAM channel: 1/15 Mega Man poses and 6/57 Contra poses recovered as distinct figures (6.7 % / 10.5 %), and 0/15 resp. 3/57 poses fit entirely inside one `sprNNN`. The cause is not the cross-pose stacking ADR-0168 §3 blames (its guard fires on 1 of 45 groups) but **under-grouping**: ADR-0153 §2's 0.80 test drops every edge from a tile that moves between poses. ADR-0168 amended in place with the evidence (still `proposed`); the recorder change is the prerequisite and is written up as `proposed` ADR-0170 — the OAM stream is already in memory at save time (`_oamFrames`), so it costs one sidecar, no new capture. Evidence: `runs/s10a-shared/S10a-summary.json`. **Re-measured 2026-09-11 on the F9.19 binary: PASS at 100 %** (25 of 25 of the main character's poses present in `poses.json`, 68 of 72 of every ground-truth pose), so the prerequisite this row asked for exists and the spike's question is answered — evidence `runs/s10a-rerun/S10a-rerun-summary.json` |
| S10.b | **Does a hosted image model preserve a contact sheet?** One subject sheet on a chroma backdrop, 1K and 2K, three prompts; measure per-cell displacement, gutter ink, whether alpha comes back, silhouette growth, cost, latency. **Run by hand, by the user, from their own account**, with the files to be sent listed before sending; nothing in the repo automates it | cells within ±1 px at 1x and gutters clean on ≥ 2 of 3 runs — else per-cell or per-row generation is the only path and the cost model changes | the BYOK/egress ADR (amends ADR-0154 §2/§4, or declines to) |
| S10.c | **Keep `generated`, keep local data out.** `mep_build.py pack` carries the root `generated` object across a rebuild; a fixture with a non-pack subfolder shows what the zip contains | `test_mep_build.py` cases, one per behavior | `mep_build.py` fix — do now, needed by F9.6 too — **done 2026-09-09** (§3); the exclusion half is documented, not implemented: it would be new policy, and the PRD's own rule (studio data outside the pack folder) is the fix |
| S10.d | **Coverage-preservation check for a painted pack.** Every tile key of the recorder's `hires.txt` still resolves after a repaint; F5.4d count unchanged | a `test_mep_build.py` / `headless_record` case a skinned pack passes and a pack with a dropped key fails | the validation rule for any generated pack (F9.6 test 8 too) — **done 2026-09-09** (§3) as `mep_build.py check-coverage`; strictness open (equality vs. "must not shrink") for the ADR this feeds |

**After the spikes.** If S10.a and S10.b pass, write the ADRs — one
decision each, by hand, via `/adr`: (i) whether and how a player's own key
may send ROM-derived crops to a hosted model (amending ADR-0154 §2/§4, or
not); (ii) the subject model and where studio data lives (outside `mep/`);
(iii) the tool contract and the validator as the gate; (iv) a reverse
channel amending ADR-0169, only if a live preview is worth more than
headless screenshots. Then slice the product work, one slice per task. If
either spike fails, the phase closes with the measured reason in §3 and the
LLM-assisted skin tool returns to "Deferred / optional".

**Risks (this phase).**

| Risk | Mitigation |
|---|---|
| ROM-derived art leaves the machine in S10.b | run by hand by the user from their own account; the sent files are listed first; nothing in the repo automates a hosted call until an ADR allows it; `sheet_repaint.py` stays loopback-only |
| Spike results read as a plan | this section names no modules, formats or slices beyond the four spikes; the ADRs come after the numbers |
| Model ids and pricing churn | recorded above as configuration with a read date; re-read before S10.b |
| Safety filter refuses franchise art | prompts describe shape and style, never franchise names; a refusal is a measured outcome, not retried automatically |

#### Prior art from the fork network (survey 2026-09-05)

**Method and headline.** All 70 forks of `nesdev-org/MesenCE` were compared
against upstream `master`; every branch that was genuinely ahead had its
changed-file list read. Twenty-one are empty mirrors, and a large share of the
remaining "ahead" branches are mirrors of upstream's own `Sour*` topic
branches rather than fork work. The load-bearing finding is a negative one:
**nobody in the fork network works on HD packs, MEP, or audio replacement** —
every `Core/NES/HdPacks/` hit traces back to a mirrored upstream branch. That
ground is ours alone, and this table exists so the survey is not repeated.

What the network *does* have is emulator automation: six people independently
built MCP / REST / JSON-RPC control surfaces over Mesen. That is our headless
harness problem, solved several ways, in readable code.

| Source | What it is | Value, and why | Where it lands |
|---|---|---|---|
| `zerkz/MesenCE` · `master` · `Core/Shared/InputOverrideProvider.{h,cpp}` (108 lines) | An `IInputProvider` that resolves buttons by name (`GetKeyNameAssociations()`), expires each override after N frames (`EndFrame = GetFrameCount() + durationFrames`), overlays instead of replacing physical input (`SetInput` returns `false`), walks `IControllerHub` sub-ports, and re-registers on `ConsoleNotificationType::GameLoaded` | **High.** It already implements two of the three properties ADR-0157 decided, in one self-contained file. Its `GameLoaded` re-registration — "a new console (and control manager) is created on every game load" — is the structural explanation of our own documented `input=` no-op trap | **F9.14** (read before designing) |
| `lusid/MesenCE` · `feature/mcp-*` (37 / 32 / 17 ahead, nothing merged upstream) · `Core/Shared/Video/BaseVideoFilter.cpp`, `Core/Shared/Emulator.h`, `UI.Tests/Mcp/` | In-memory frame capture; a packed `atomic<uint64_t>` carrying a **boundary epoch** plus per-owner-thread debug-request accounting (`873730e5`, `03f99a40`), so an external caller can tell "the emulator stopped for *my* request" from "it stopped for someone else's"; and ~7k lines of xUnit against a fake core | **High.** The capture and the test model are direct slices below. The epoch scheme addresses an ambiguity our harness has but has never named — worth reading before we extend stop/resume handling | **F9.15**, **H9**; epoch scheme = reference |
| `ky12138/MesenCE` · `master` (36 ahead) · `Core/Debugger/MappingTracker.{cpp,h}` (`fdc6b156`), `AddressPage.h` | Tracks NES PRG/CHR bank mapping **over time**, with cache persistence | **Medium, reference only.** ADR-0153 / F9.7 already names "CHR bank swaps, CHR-RAM re-uploads" as the source of the duplicate vocabulary entries the alias pass collapses *by pixels*. Bank-aware identity would attack that at the source. No slice opened: we do not yet know whether the ink-share alias budget leaves residual error this would fix | F9.7 follow-up (no slice) |
| `ky12138/MesenCE` · `adc1a6a2`, `42e0ee27` | `NES_ONLY` / `LessUI` compile-time build modes | **None, on measurement.** Both commits are C#-only — they exclude `UI/` files from the csproj and never touch `Core/`, so no core was ever compiled out. Against this tree the removable surface is 4 Netplay window files; the rest is product (GB/GBA/SMS UI, the HD Pack builder, the recorder) or already deleted by the console reduction | **H8** — declined and closed, **ADR-0158** (accepted 2026-09-05) |
| `mmg-media/MesenCE-debug` · `master` (43 ahead) · `Core/SNES/Debugger/SnesDebugLog.{h,cpp}`, `c8cc701a`, `76af74d5` | An always-on ring buffer of ROM reads plus DMA/transfer capture, then a reverse search for which ROM addresses produced the tiles/palette currently on screen | **Medium, reference only.** Tile provenance is adjacent to ADR-0043 (static ROM tile export) and to metatile identity, but this is SNES-implemented: a technique to port, not code to lift. The fork also deletes all CI workflows and mixes in a trainer — quarry, not a branch to merge | Reference |
| `Hoshiruna/MesenGM` · `develop` · `MCPServer/`, `Core/Shared/Video/TrueTypeFont.{cpp,h}` | An *out-of-process* MCP server (the alternative shape to lusid's in-process one), and TTF/embedded-bitmap fonts wired into `DebugHud` | **Low.** Recorded for the architectural contrast; the TTF work only matters if we ever want legible labels burned into captures or sheets | Reference |
| `michaelcmartin/MesenCE` · `tms-magshift` · `2cc3ea1b` | One line in `SmsVdp::ShiftSpriteSg` clipping magnified sprites under Early Clock | **Low.** Verified absent from our tree, but `ShiftSpriteSg` is the SG-1000 / ColecoVision TMS9918 path, not the SMS path our product consoles use | Not planned |
| `Schaltfehler/MesenCE` · `feature/lua-debugger-surfaces` (16 ahead) | 1382 lines exposing access counters, CDL, trace, callstack and profiler to Lua | **Low.** A scripting alternative to a socket/automation surface; Lua-in-emulator is a worse fit for our harness than an in-process provider | Not planned |
| `NovaSquirrel/Mesen2` · `gb-link-cable`; `eclectic-sh/MesenCE` · `SourTestUpdate`; `HeeminTV` · `mmc5_pcm_irq` | GB dual-console plumbing; `RecordedRomTest` MD5→SHA1 / `MRT`→`MT2`; MMC5 PCM IRQ | **None — already ours.** Each verified present in our tree (e.g. `MT2` and `SHA1::GetHash` in `Core/Shared/RecordedRomTest.cpp`). Listed so they are not re-reported as new | Already merged upstream |
| 21 empty mirrors; ~6 mutually redundant localisation forks; WonderSwan / GBA / SNES / Mega Drive / packaging forks | — | **None.** Off-product consoles or no content | Not planned |


### 5. Order of execution

1. ~~Phase 6 · H1–H10 · Phase 5 · D1–D13 · input tester · Phase 7 · Phase 8
   · Phase 9 F9.0–F9.17~~ — shipped (§3).
2. **Phase 9 F9.18** (composition editor GUI + human panel) — independent of
   Part B. Run the human panel *after* F9.19 (§3): the sprite layer now has
   poses to compose, so the panel judges the intended unit instead of
   re-reporting the fragment defect ADR-0170 already measured.
3. **Phase 10 feasibility spikes** — S10.c, S10.d and S10.a all ran
   2026-09-09 (§3): the two pack-side ones shipped and S10.a failed. The
   user resolved that on 2026-09-11 by accepting ADR-0170, shipped as F9.19,
   and **S10.a re-measured the same day at 100 %** (§3). Still open: S10.b,
   which needs the user's key and hand. No product slice is scheduled.
4. Manual and hardware residue, opportunistically: F6.5 file-picker step,
   Phase 5 listening pass, input tester with a pad, Phase 9 validation
   test 8 (needs a local diffusion stack).

### 6. ADR map

One line per decision. Chronology, amendments and evidence live in the ADR
files and in §3.

| ADR | Status | Meaning for this roadmap |
|---|---|---|
| 0040/0044/0047/0049/0050/0052/0120/0121 | accepted | shipped foundations — storage, permissive targets, fingerprints, sibling convention, `<background>` capture, level-2 audio, zip discovery fallbacks; do not diverge without amending |
| 0122/0126/0127/0129/0130 | accepted | unit-test and CI wiring (`UI.Tests`, `core_unit_tests`, extracted-helper pattern) |
| 0123/0124/0125/0128/0131/0136/0137 | accepted | H-series hygiene: firewall parity, fixture format, test helpers, ThrowsAny, CI contract, `mep_compare` dispatch, `make doc-checks` |
| 0051/0132/0133/0134/0135/0142 | accepted (0134 = Option A) | Phase 5 audio: sound-driver discovery, variant cap, mute mask, loop point, Extract Audio contract, crossfade |
| 0138 | accepted, amended in place (D5) | Phase 6 design; F6.0–F6.8 shipped |
| 0139/0140/0141 | accepted | Part B identity: `content_id`, `pack_id`, one slot per `pack_id` with the `content_id` update trigger (amends 0138 §37) |
| 0143/0144/0145/0146/0147/0148 | accepted | one slot per game; audio via bundled patch; optimistic matching; auto-load every accepted pack (supersedes 0138's consent clauses); `auto/` + `mep/` siblings; self-contained catalog rows |
| 0149 | accepted | Phase 8 border layer (MEP v1.5) |
| 0150 | accepted | Avalonia.Headless XAML-wiring tests (`UI.HeadlessTests/`) |
| 0151/0152 | accepted | unresolvable `<background>` is a lint error; known-missing errata (F6.8) |
| 0153/0156/0159/0160/0164/0166 | accepted (0153 amended by F9.12/F9.16) | Phase 9 sheets: vocabulary + grouping + maps; screen residency; save-time anchors; `textures/chr/`; adjacency sidecar; screen ownership of nodes |
| 0154 | accepted (Option A) | F9.6 external repaint, loopback-only, `generated` as disclosure not gate; Phase 10 S10.b measures whether an amendment of §2/§4 is worth proposing — until then it stands as written |
| 0155/0157/0158/0163/0167 | accepted | `-MMD -MP`; frame-counted headless input; no `NES_ONLY`/`LessUI`; fork–upstream coexistence; HUD-only capture |
| 0161 | proposed | positional palette-variant correspondence (F9.6 §5) |
| 0162 | proposed | accuracy suite as a regression gate (H10); not in CI by decision |
| 0165 | accepted | F9.18 composition editor: external stdlib tkinter tool over a host-free engine |
| 0168 | **superseded** (2026-09-11) by ADR-0171 | figure (`sprNNN` group) as the unit — S10.a measured the walk at 6.7 % / 10.5 %, so the answer was retired and the principle kept; §2/§3 stay readable as the specification of the fallback path for a pack recorded before ADR-0170 |
| 0171 | accepted (2026-09-11) | the sprite layer's unit is the **pose** (ADR-0170's `poses.json`), the `sprNNN` figure is the fallback and the bare node the degenerate case; fixes the ranking denominator ADR-0168 left open and accepts contact-merged poses. Implementing slice: F9.18's sprite layer |
| 0169 | accepted | recorder publishes frames one way; the live viewer never blocks the run |
| 0170 | accepted (2026-09-11) | the recorder writes `sheets/poses.json` from the OAM stream it already holds; shipped as F9.19, and the prerequisite S10.a named |

### 7. Risks

| Risk | Mitigation |
|---|---|
| Project framed as a distributor of derivative content | catalog holds URLs + hashes + licenses only; client never scrapes third-party hosts; user supplies unlicensed audio |
| Recipe vocabulary grows into a scripting language | new op = new `recipe` major + new ADR; clients skip unknown versions |
| Two agents implementing the same ADR in parallel | one task per slice; accepting an ADR is a request for work, so say which agent owns it before implementing — no background runner claims `accepted` ADRs any more (the dev-squad plugin was removed on 2026-09-03) |
| Upstream pack drift after acceptance | sha256 in the catalog + drift check; client reinstalls when the slot's `content_id` changes (ADR-0141) — a wrapper-only sha256 change does not reinstall |
| Catalog-shaping decisions recorded only in issue comments or commit messages (the 2026-08-31 audio-only NEA removal) | every such decision gets an ADR or a PRD line the same day (ADR-0148 backfilled the one already made) |
| ADR files deleted by an unrelated commit go unnoticed (0130/0131/0136/0137, 2026-08-28) | restored (D1); `scripts/checks/verify_adr_refs.py` in `make doc-checks` fails on a dangling `ADR-NNNN` reference |
| Scope explosion | phases independent; GitHub is the only backend; no telemetry |
| Phase 10 sends ROM-derived art to a hosted model | only S10.b does, by hand, by the user, from their own account, with the files listed first; no tool in the repo automates a hosted call until an ADR amends ADR-0154 §2 |
| Phase 10 spikes read as a product plan | the section names no modules, formats or product slices; ADRs are written after S10.a/S10.b report numbers |
| Phase 9 judged by pixel metrics instead of legibility (F5.4e "shipped" green while emitting no sheet on any real game) | the human validation panel in Phase 9 is the acceptance gate; a slice is not "shipped" until its cold-read / find-and-edit rows are logged for at least two golden games |

### 8. References

- SUPER ZSNES — https://www.zsnes.com/ · VGMusic · romhack.ing · Zeldix (MSU-1, other hosts)
- No-Intro DATs — https://no-intro.org/ · rcheevos `rhash` · vgmrips (VGM/GD3) · beat/BPS spec
- Precedents: *MGM v. Grokster* (2005); Yuzu/Nintendo settlement (2024)

---

## Part B — Player shell (default GUI)

**Status:** **Phase 7 shipped — P.0–P.7** (2026-08-28 → 2026-09-01; record
in Part A §3). Product text of §3–§6 accepted by the user 2026-08-28. Manual
residue: the native file picker (F6.5) only — the letterbox fit was closed
2026-09-05 (`RendererViewportFit`, `UI.HeadlessTests/RendererLetterboxTests.cs`);
the cards, the Player Settings tabs and the picker's arrow navigation are
asserted by `UI.HeadlessTests/` (ADR-0150) and the aspect-ratio math by
`core_unit_tests` Bloco N ·
**Author:** sbihaiko ·
**Scope:** MesenCE fork (`main`); nothing goes upstream ·
**Parent roadmap:** Part A of this document (Phase 7 entry). Pack/core work
stays there; this Part owns chrome, pack identity, duplicates, and the
player-facing choice between packs ·
**Specs:** [MEP-v1](../specs/MEP-v1.md) · [MEI-v1](../specs/MEI-v1.md) ·
[MEP-recipe-v1](../specs/MEP-recipe-v1.md) ·
**Decisions:** identity model (§3) and one-slot rule (§3.6) are accepted
product requirements, specified by ADR-0139 (`content_id`), ADR-0140
(`pack_id`, catalog uniqueness) and ADR-0141 (one slot, client update
trigger — amends ADR-0138 §37). Chrome (§6) is a product requirement;
`UiMode` has no ADR and needs one only if a trade-off beyond §6 appears ·
**Process:** one task per **slice** (P.1, P.2, …). Settle the slice's ADRs
first. A slice is done when its acceptance checks pass and this header plus
Part A's Phase 7 entry are updated.

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
channel carries URLs + hashes + licenses, never third-party assets; hosts
never execute pack content as code; no LLM in the client (a Phase 10 skin
tool, if its spikes pass, would be an external tool like the live viewer;
the shell contributes nothing until an ADR says otherwise).

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

Exact canonicalization (path order, which files, newline folding, zip
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
`MepRecipeInstaller`, write into the `<sibling>/mep` folder with a central
fallback (ADR-0147), then the scan above applies it. The
`AutoInstallCommunityPacks` toggle stays in F6.4b; the first-run consent it
once carried was removed by F6.7 (ADR-0146).

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
  patch), license (or "not declared"), and catalog 👍 as **sort key**, not
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
area) is the seventh entry here (implemented in Phase 8 F8.2, commit `6dc13f9e`,
gated by `EnhancementPackConfig.EnableBorder` and backed by `border.png` + optional
`border.json`). It lives beside the other enhancement toggles in `PlayerEnhancementsPanel`.

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

Architecture slices need their ADR accepted first. All eight shipped;
the one-line record is Part A §3 and the decisions are §9 below.

- **P.0** — ADR-0139/0140/0141 accepted (2026-08-28).
- **P.1** — `content_id` in `scripts/` and in the Core, mep-meta +
  `.mep-install.json`, golden parity (2026-08-29).
- **P.2** — catalog / mep-meta / MEI identity fields, one slot per `pack_id`
  (2026-08-29).
- **P.3** — per-ROM preference resolver + Advanced picker (2026-08-29).
- **P.4** — `UiMode` default rule, Player chrome, overlay, Esc precedence in
  the shortcut config (2026-08-29).
- **P.5** — Player pack UX: picker decision + panel, current-pack chip, apply
  toast (2026-08-29).
- **P.6** — §3.6 catalog update trigger wired into F6.4b; wrapper-only change
  does not reinstall, no auto-downgrade, a removed slot keeps its install,
  votes sort the picker (2026-08-29).
- **P.7** — Enhancements quick-toggle panel + welcome/Continue cards, §6.1–§6.2
  (2026-09-01); XAML wiring asserted by `UI.HeadlessTests/` (ADR-0150);
  the letterbox fit closed 2026-09-05 (`RendererViewportFit`).

### 9. ADR map

| Topic | Status | Meaning |
|---|---|---|
| ADR-0139 — `content_id` algorithm (tree canonicalization, recipe composite, excluded files, `version` string excluded, two implementations + parity) | **accepted** (2026-08-28) | P.1 was built on it |
| ADR-0140 — `pack_id` (MEP `id` field; `owner/repo`; `issue-n`; `local:<container>`) + catalog uniqueness + origin binding (amended 2026-08-28) | **accepted** (2026-08-28) | P.2/P.3 were built on it. §3.6 is accepted product text — the ADR specifies enforcement |
| ADR-0141 — one live slot per `pack_id`; amends ADR-0138 §37 (client update trigger `source.sha256` → `content_id`); no auto-downgrade; removed slot keeps install | **accepted** (2026-08-28) | P.6 shipped 2026-08-29 on this trigger; ADR-0138 §37 now carries the in-place note pointing here (Part A §3, D5) |
| ADR-0143 — one slot per **game**: `pack_id` = origin × game; multi-game zip → N packs + N `pack:split` sibling issues | **accepted** (2026-08-29) | amends §3.3 rule 2 above and ADR-0140 source 2; eight of the nine LiQuiDz siblings were later removed from the catalog as audio-only NEA (Part A §3, D4 / ADR-0148) |
| Player chrome (`UiMode`, overlay contents, overlay shortcut, upgrade default Advanced) | not needed — P.4 shipped within what §6 states | P.4 |
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
canonicalization; MEP `id` field now; duplicate-submit policy; silent
`local:` → catalog `pack_id` migration) were closed by ADR-0139/0140/0141
on 2026-08-28 (hash: ADR-0139; `id` as MEP v1.4 SHOULD, comment + close
the newer duplicate issue, silent migration: ADR-0140). New questions go
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
