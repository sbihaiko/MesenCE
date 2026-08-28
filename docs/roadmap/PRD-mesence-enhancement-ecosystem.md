# PRD — MesenCE Enhancement Ecosystem (consolidated roadmap)

**Status:** active (2026-08-27) — the single planning document of this fork. Earlier plans (`PRD-ecossistema-enhancement-comunitario.md`, `PRD-community-pack-mep-conversion.md`, `plano-execucao-F3.md`, `plano-execucao-F5.md`, `plano-reducao-consoles.md`, `plano-host-input-tester.md`) were consolidated here and deleted on 2026-08-27; their full text lives in git history. ·
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
| **F6.4** client installer | `MepRecipeInstaller` (Core): fetch catalog (ETag cache in the MEP `.cache`), match ROM by No-Intro sha1, download primary within the CI host allow-list, verify sha256, prompt for `user_supplied` deps with hints + licence, run ops, write `pack.json` + `.mep-install.json`; reinstall when `source.sha256` changes; setting `AutoInstallCommunityPacks` (default on for packs without user-supplied deps; prompt otherwise); UI notice when the patch is withheld | headless: synthetic catalog + split pack → installed folder equals `mep_recipe.py apply` output byte-for-byte; hash mismatch aborts; missing dep → no patch, textures still applied |
| **F6.5** rollout | `/revalidate` #65/#66/#68/#69/#71; update this header | all five `pack:valid` + `assets:external`; one of them installed end-to-end in the GUI with user-supplied audio |

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
  after Phase 6, if the catalog grows past what a list can show.

## 5. Order of execution

1. **F6.2 → F6.3 → F6.4 → F6.5**, one run each.
2. **H4** at any time (small, independent, no Core impact). H1–H3 shipped.
3. **Phase 5 Blocks B–D** after the user accepts ADR-0133/0134/0135 and
   decides the SoundFont question; **F5.4c/d** can run before that.
4. **Input tester I.0–I.2** independent of everything above.

## 6. ADR map

| ADR | Status | Meaning for this roadmap |
|---|---|---|
| 0138 | accepted | Phase 6 design; F6.0 and F6.1 shipped; remaining work list = F6.2–F6.5 |
| 0137, 0131, 0124, 0136 | accepted 2026-08-27 | H1–H4 |
| 0121 | accepted 2026-08-27 (option A, shipped `805cb10d`; §2.1 rule 9 wording shipped with F6.1) | legacy bare `hires.txt` fallback is the norm |
| 0132 | accepted | F5.4b follow-ups (a)/(b) |
| 0133, 0134, 0135, 0051 | proposed | gate Blocks C/D — user decision |
| 0123, 0125, 0128 | proposed | H5–H7 — not blocking |
| 0040/0044/0047/0049/0050/0052/0120 | accepted | shipped foundations; do not diverge without amending |

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
