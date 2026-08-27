# Execution plan — Phase 3: Unified pack format (MEP v1)

**Status:** done (2026-08-24; manual GUI validation of the window pending from the user). After this the fork dropped SNES/PCE/WS/Coleco (`plano-reducao-cores.md`): MSU-1 and Coleco/SNES hashing in this document are phase history, not part of the product. — F3.0 ✅ (ADR-0038…0042 in `.dev-squad/adr/`), F3.1 ✅ (core validated headless on 2026-08-24: dir+zip match on NES/GB, badhash ignored, badjson/major/zip-slip rejected), F3.2 ✅ (delegations validated headless: GB textures via MEP → screenshot 1:1 against the baseline; loose HdPacks/ wins with log; NES textures+audio(1 BGM/1 SFX)+synth; pack ESP applied on NES/GB — log `[MEP] synth`), F3.3 ✅ (EnhancementPackConfig + C# mirror, exports GetMepPackList/GetMepRomSha1/SetMepPackEnabled, "Enhancement Packs" window in the HD Packs menu; toggles validated headless via the harness's `mep-*` flags; dotnet build 0 warnings), F3.4 ✅ (golden tree, E2E zip NES textures+bgm+synth, F1/F2 regressions, README) ·
**PRD:** [PRD-ecossistema-enhancement-comunitario.md](PRD-ecossistema-enhancement-comunitario.md) §Phase 3 ·
**Spec:** [MEP-v1.md](../specs/MEP-v1.md) (published) ·
**Process:** resolve the phase's ADRs (F3.0) before any code, as in phases 1 and 2.

## Success criteria (PRD)

> A single `.zip` links textures + OGG track + synth preset for a game,
> with each piece independently toggleable.

Validation target: an NES game (e.g., Mega Man 3) — hires.txt textures + OGG
BGM (via the `<bgm>` tags in hires.txt itself, already supported by
`HdPackLoader`) + ESP preset, in a single MEP pack, with independent toggles
per section. OGG for GB/SMS depends on the freeze of the hires-gbsms
extension (draft §3.4, under review in issue #1) and is explicitly **out**
of this phase (see proposed ADR-0041).

## State of the ground (verified in code on 2026-08-24)

| Integration point | Status |
|---|---|
| JSON parsing in the C++ core | **Does not exist**: no JSON parser in Core/Utilities — decision needed (ADR-0038) |
| No-Intro hash | **Does not exist**: `Emulator::GetHash(Sha1)` hashes the whole file; `NesConsole::GetHash(Sha1Cheat)` is PRG only. NES No-Intro = file minus the iNES header (16B) and minus the trainer (512B, flags6 bit 2) — computable directly from the file, without a mounted console |
| NES textures | `HdPackLoader::LoadHdNesPack(string definitionFile, ...)` already accepts an arbitrary hires.txt path and reads from **zip** (ZipReader) — trivial delegation |
| GB/SMS textures | `HdTilePack::LoadFromFolder(folder, ...)` already exists (created in the post-F2 consolidation) — directory only, no zip |
| NES OGG audio | `<bgm>`/`<sfx>` tags in hires.txt via `OggMixer` — already works |
| GB/SMS OGG audio | the v1 loader ignores the tags (log "not supported yet") — out of F3 |
| MSU-1 | was SNES-only; the SNES core was later dropped (`plano-reducao-cores.md`). Out of F3 and out of the product |
| ESP preset | `EnhancedSynthPreset` reads `EnhancedAudioPresets.cfg` from the home directory on reset/load — needs an intermediate override layer (defaults < pack < user file, MEP spec §5.3) |
| Zip | `Utilities/ZipReader` (miniz) available |
| Spec validation | `scripts/validate-specs.py` already validates the golden `pack.json` |

## F3.0 — Phase ADRs (blocks the rest) ✅

1. **ADR-0038 — Core JSON parser.** There is no parser in the core. Options:
   (a) a minimal in-house parser in `Utilities/` (~200 lines, strict JSON,
   objects/arrays/strings/numbers/bool/null, error = invalid pack);
   (b) a header-only lib (nlohmann, ~25k lines). Recommendation: (a) — the repo
   avoids dependencies, pack.json is small, and the golden file becomes a test.
2. **ADR-0039 — Per-console No-Intro hash.** New `HashType::Sha1NoIntro`
   resolved by the host from the *file* (MEP spec §4 table): NES skips the
   header/trainer; GB/GBC/SMS/GG/SG = whole file (Coleco/SNES were in the ADR's
   table; they were dropped from the product afterward). Where it lives: a static
   function in the MEP manager (does not require a mounted console — matching
   runs before `console->LoadRom`).
3. **ADR-0040 — Storage, discovery, and precedence.** Central folder
   `EnhancementPacks/` in the home directory; each pack = subdirectory
   `<name>/pack.json` **or** a loose `<name>.zip`. Matching by
   `targets[].sha1` (case-insensitive). Precedence (spec §5.1): a loose HD
   Pack in `HdPacks/<rom>/` **wins over** the textures section of any MEP;
   among MEPs, define and document the deterministic order (proposal:
   case-insensitive lexicographic order of the container name — reproducible
   across machines, unlike the spec's "install order" suggestion, which
   depends on mtime). Zip for GB/SMS: direct reading via ZipReader in
   `HdTilePack` **or** transparent extraction to a cache on install — decide
   here.
4. **ADR-0041 — v1 audio scope.** The `audio` section in v1 = OGG via
   hires.txt (NES). GB/SMS deferred until the draft extension freezes; MSU-1
   deferred (SNES out of the phases and, later, out of the host). Document in
   the README/spec as a host limitation (the MEP spec stays as is — the
   limitation is in the implementation).
5. **ADR-0042 — ESP override layer.** Application order: built-in defaults →
   pack preset (`synth` section) → the user's `EnhancedAudioPresets.cfg`
   (the user always wins, spec §5.3). Mechanism: an extra step in
   `EnhancedSynthPreset::LoadOverrides` with the path/content coming from the
   manager.

## F3.1 — Core: parsing, matching, and hash-based loading ✅

**Delivery:** opening a ROM automatically loads the applicable MEP packs.

- `Utilities/JsonReader.{h,cpp}` (new, per ADR-0038) + usage in the golden test.
- `Core/Shared/EnhancementPacks/MepPack.{h,cpp}`: parsing/validation of
  `pack.json` (MUST fields, semver, hash formats, rejection of `..`/absolute
  paths — zip-slip, spec §2.3/§6; unknown fields ignored §3.2; unknown `mep`
  major rejected §3.1).
- `Core/Shared/EnhancementPacks/MepPackManager.{h,cpp}`: scans the central
  folder (directories + zips), matching by No-Intro sha1 (ADR-0039), a list
  ordered by precedence (ADR-0040), API for the consoles:
  `GetTexturesPath(system)`, `GetSynthPreset()`, section flags.
- `Emulator::LoadRom`: instantiate/rescan the manager **before**
  `console->LoadRom` (the consoles load HD packs inside their own LoadRom).
- vcxproj/filters + **clean all `.o` files** (SettingTypes.h and new headers —
  the makefile has no header deps; symptom of forgetting this: heap corruption).
- **Validation:** headless test with a directory pack and a zip pack
  (generated by the new python script `scripts/gen_mep_test_pack.py`),
  correct hash matching (NES with/without iNES header), invalid pack rejected
  with a log entry.
  **Done:** `scripts/headless_record <rom> 1 <prefix> screenshot log` with
  the packs generated in `<prefix-dir>/mesen-home/EnhancementPacks/` — the
  core log (`[MEP] ...`, new harness flag `log`) shows matches and
  rejections. Note: the `GetLog` export already existed; F3.3 adds
  `GetMepPackList`.

## F3.2 — Section delegation (textures + synth + audio-NES) ✅

**Delivery:** pack content reaches the existing subsystems.

- **textures/NES:** in `NesConsole::LoadRom` (line ~256), when there is no
  loose `HdPacks/<rom>/hires.txt` (precedence!), ask the manager for the path
  and call `HdPackLoader::LoadHdNesPack(definitionFile, ...)`.
- **textures/GB/SMS:** same idea in `Gameboy::LoadRom` / `SmsConsole::LoadRom`,
  via `HdTilePack::LoadFromFolder` (with ADR-0040's answer for zip).
- **synth:** apply ADR-0042 across the three engines (NES/GB/SMS EnhancedSynth).
- **audio/NES:** OGG comes in through the textures section's hires.txt tags
  (or an audio-only hires.txt in the audio section — final form in ADR-0041).
- **Headless validation:** MEP pack with neutral GB hires → screenshot 1:1
  (reuses the `screenshot` harness); pack with ESP preset → capture MIDI and
  check for a GM program change vs. default; precedence: loose HdPacks +
  MEP simultaneously → the loose one wins.
  **Done** (2026-08-24): `gen_mep_test_pack.py ... dir --textures=<rec-hdpack>`
  + `headless_record ... screenshot log`; PNG byte-identical to the baseline
  with and without the loose pack. The pack's ESP does not change MIDI
  notes/programs (DSP only), so verification is via the log `[MEP] synth:
  applied ESP overrides` — F3.3 can expose the effective preset via interop
  if needed. SMS not tested (no test ROM available), but it uses the same
  `HdTilePack::LoadForRom`.

## F3.3 — Granular toggles + UI (PRD's F3.2) ✅

**Delivery:** each section toggleable in the UI; packs visible and manageable.

- `SettingTypes.h`: `EnhancementPackConfig` (global EnableMepPacks +
  EnableTextures/EnableAudio/EnableSynth per section; disabling an individual
  pack by name persists in config). New fields **at the end** of the structs
  + the C# interop mirror (`[MarshalAs(I1)]`, appended at the end).
- UI: "Enhancement Packs" window (lists packs applicable to the open ROM,
  a checkbox per pack and per section, an Install button that extracts a zip
  into the central folder — reusing the `InstallHdPack` flow); menu item
  visible for NES/GB/SMS. A toggle change = reload of the affected subsystem
  (`ForceFilterUpdate` for textures; reset for synth).
- InteropDLL: exports `GetMepPackList`/`SetMepPackEnabled` (or equivalent).
- **Validation:** dotnet build 0 warnings; toggles reflected headless via
  config (the harness can set EnhancementPackConfig through the real struct).

## F3.4 — Phase close-out ✅

- Golden/example: a demonstration MEP pack in `docs/specs/golden/mep/`,
  complete (the pack.json already exists; add a minimal example tree).
- E2E for the success criterion: a zip with textures + `<bgm>` OGG + ESP
  preset for an NES game, each section toggleable — validated headless +
  manual GUI.
- F1/F2 regressions (existing headless suite), clang-format, DOX pass,
  README (Phase 3 ✅), project memory update.

**Done (2026-08-24):** `docs/specs/golden/mep/` gained `textures/` (neutral
GB pack recorded from the F1 Test Tone), `synth/preset.cfg` (a copy of the
golden ESP), and `audio/README.md` (GB out of the v1 host — ADR-0041); the
golden loads in the host (log `[MEP] textures ... 78 tiles` + `[MEP]
synth`). E2E for the criterion: an NES zip with textures + hires.txt
`<bgm>`/`<sfx>` + ESP preset → all three sections applied and each one
toggleable (`mep-notextures`, `mep-nosynth`, `mep-disable=`). Regression:
GB and NES MIDI/VGM without packs OK. **Pending from the user:** open the
window in the GUI (`! open -a ...`) and check the list/Install. Runtime
toggles follow the same rule as `EnableHdPacks` (next power cycle);
`ForceFilterUpdate` for textures was left out (v1).

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Init order in `Emulator::LoadRom` (the manager needs the hash before the console) | No-Intro hash computed from the file (ADR-0039), without depending on a mounted console |
| Stale `.o` after changing SettingTypes.h/new headers | clean `Core/`, `Utilities/`, `InteropDLL/` before every `make core` in the phase |
| C#↔C++ interop misaligned (config structs) | fields always appended at the end; the harness includes the real `SettingTypes.h` (drift breaks the compile) |
| Zip-slip / malicious pack | central validation in MepPack (spec §6), dedicated negative test |
| Runtime toggle destabilizing the console | v1: toggles apply on the next load/reset (same as the current EnableHdPacks), except textures (ForceFilterUpdate is safe) |

## Suggested session sequence

1. **Session A:** F3.0 (ADRs 0038–0042) + F3.1 (headless-validated core).
2. **Session B:** F3.2 (delegations + precedence validation).
3. **Session C:** F3.3 (config/interop/UI) + F3.4 (close-out, E2E, README).

## Addendum (2026-08-25) — Export ROM Tiles (out of F3 scope, requested by the user)

**Export ROM Tiles** button in the HD Pack Builder (`ExportRomTilesHdPack`):
NES dumps the entire CHR ROM as `defaultTile` (8192 tiles for Mega Man 3;
Zelda refused because it uses CHR RAM); GB/SMS scan the ROM for uncompressed
tiles (partial coverage; F1 Test Tone: 12 bitmaps, none of the 26 displayed
— they're generated at runtime). Re-recording on top merges while preserving
the defaults (GB 24→102, NES 8192→8300). Harness: `romtiles` flag. ADR-0043.
