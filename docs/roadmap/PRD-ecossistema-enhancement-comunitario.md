# PRD — Community Enhancement Ecosystem (MesenCE)

**Status:** draft ·
**Author:** sbihaiko ·
**Date:** 2026-08-23
**Scope:** MesenCE fork

---

## 1. Context and motivation

MesenCE already has **Enhanced Audio** (a synth running in parallel to the accurate APU, per-game presets in `EnhancedAudioPresets.cfg`, coverage for NES / GB / SMS+FM). The relaunch of **SUPER ZSNES** (zsnes.com, v0.300, 2026) commercially validated the same thesis with its
"Super Enhancement Engine": curated improvements game by game (manual hi-res, texture/normal maps, widescreen, overclock, audio replacement), all individually toggleable,
with enhancement data kept separate and free of copyrighted content.

This PRD defines the natural evolution of that thesis in MesenCE: turning the emulator into
a **platform for extracting, authoring, and consuming enhancement packs**, with the community
producing the content — while keeping the project legally clean.

Mesen already has ready-made foundations in the cores this fork keeps (NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA — see `plano-reducao-cores.md`):

| Foundation | Where | What it gives for free |
|---|---|---|
| NES HD Packs (HDNes format) | `Core/NES/HdPacks/` | Tile replacement + OGG audio (`OggMixer`), context conditions, **HD Pack Builder** (tile recorder) |
| GB/SMS HD tiles | `Core/Shared/HdPacks/` + `HdTilePack` | Same tile envelope for handheld/SMS; OGG on these systems still depends on the hires-gbsms extension |
| Enhanced Synth Engine | `Core/Shared/Audio/EnhancedSynthEngine.*` | Tap that already converts register state into note/voice abstractions — ~90% of a MIDI exporter |

This fork does **not** emulate SNES. MSU-1 (`Core/SNES/Coprocessors/MSU1/`) left with the core; it's not a foundation of the product.

## 2. Goals

1. Let any user **extract locally** the visual and music assets of the
   game currently running (tiles → PNG; music → MIDI/VGM).
2. Define a **unified pack format** (textures + audio + synth preset),
   identified by ROM hash, editable by the community.
3. Provide **pack discovery and installation inside the UI** (pack browser), with
   usage-based ranking, consuming configurable manifests.
4. Provide an **offline AI pipeline** that generates a first draft of packs
   (tile upscaling, assisted preset tuning), for the community to refine by hand.

### Non-goals (explicit)

- **Not** hosting, bundling, or distributing derivative content (extracted MIDIs, covers,
  third-party redrawn textures) in any project repository.
- **Not** embedding any P2P/torrent sharing mechanism in the emulator
  (inducement liability risk — *MGM v. Grokster*, 2005; Yuzu precedent, 2024).
- **Not** monetizing packs or the distribution channel.
- **Not** sending anything upstream (work lives only in the fork).

## 3. Legal architecture principles

Music copyright has two layers: the **recording/code** (we escape this: generated MIDI
doesn't contain ROM bytes) and the **composition** (there's no escaping this by format: extracted MIDI is
a transcription of the work, like sheet music). The same applies to extracted tiles. Therefore:

1. **Distribute the tool, never the files.** Extractors are legal
   (interoperability); the outputs stay on the user's machine.
2. **Official channel only carries clean content:** synth presets, hash mappings,
   manifests, tools, licensed original compositions (CC).
3. **Derivative content circulates in existing community hubs** (VGMusic for MIDIs,
   individual GitHub repos + romhack.ing for textures; Zeldix continues to exist for MSU-1
   on other emulators, not on this host), which have already absorbed
   takedown risk for decades. The emulator only consumes manifests the user points it to.
4. **The emulator is content-dumb:** no endorsement, bundling, or default that
   points to derivative material.
5. Risk factors to police in any associated hub: monetization, pre-patched
   ROMs, bundled original assets, trademarks in the name.

## 4. Standards

General rule: **adopt an existing community standard whenever one exists; formalize as an open spec only what doesn't exist** — so other emulators and pack authors can implement it without depending on MesenCE.

### 4.1 Existing standards adopted

| Area | Standard | Application | Benefit |
|---|---|---|---|
| ROM identification | No-Intro (Logiqx XML DATs, CRC32/MD5/SHA-1) | Key for packs and manifests (F3/F4) | Interop with RetroArch, existing collections and databases |
| Per-system hash | rcheevos `rhash` | Hash calculation when the system hashes only part of the file | Future compatibility with RetroAchievements |
| Audio log | VGM v1.71+ with GD3 tags | F1.1 exporter | Plays in any VGM player (foobar2000, in_vgm); metadata in the vgmrips standard |
| Score/notes | SMF type 1 + General MIDI | F1.2 exporter | Opens in MuseScore/DAWs without conversion |
| Textures | HDNes `hires.txt` (Mesen is the reference implementation) | F2/F3 | Existing authors and tools already master the format |
| NES audio | OGG via HD pack (`OggMixer`) | F3 | Already supported; part of the HDNes standard |
| Patches | BPS (beat) | If packs include ROM patches | Validates the source ROM's checksum — fits the hash-keyed model |

The only gap without an established standard: replacement audio for **GB/SMS** (MSU-MD covers only Mega Drive) — covered by the extension proposed in 4.2.3.

### 4.2 New standards to formalize (open specs)

Each spec lives in `docs/specs/<sigla>-v<N>.md`, licensed **CC0** (public domain — any emulator can implement it), containing: normative fields in RFC 2119 language (MUST/SHOULD/MAY), semver versioning, canonical example files ("golden files"), and a validation script. Changes go through issue/PR in the spec's repository; breaking change = major version bump.

**4.2.1 ESP — Enhanced Synth Preset (v1).** Formalization of the current `EnhancedAudioPresets.cfg`: the file's grammar, per-chip voice parameters (NES APU, GB APU, SMS PSG, YM2413), valid ranges for each parameter, default behavior for omitted fields, and fallback rules (per game → per chip → global). It's the only 100% new format in the ecosystem — there's no market equivalent.

**4.2.2 MEP — MesenCE Enhancement Pack (v1).** The Phase 3 envelope: a `.zip` with `pack.json` at the root. A thin shell that only **composes** existing standards: identification by No-Intro hash, metadata (name, author, license, semver version), and optional sections pointing to already-standardized formats — `textures/` (hires.txt), `audio/` (OGG on the NES host; GB/SMS via the 4.2.3 extension), `synth/` (ESP). Each section declares itself individually toggleable (granular toggle, F3.2). This host doesn't load MSU-1.

**4.2.3 hires.txt extension for GB/SMS (proposal).** Backward-compatible extension of the HDNes format using the existing `<ver>` field: new tags for GB/SMS PPUs (CGB palettes, VDP modes) and for OGG audio replacement on those systems (the gap identified in 4.1). The proposal should be discussed with the HDNes/Mesen community before freezing v1.

**4.2.4 MEI — MesenCE Enhancement Index (v1).** The Phase 4 discovery manifest: `manifest.json` with the list of packs (name, game, No-Intro hash, URL, artifact checksum, license). Indexes are **federated**: anyone can publish a MEI and the user points the emulator at it (F4.3) — the official index is just one more MEI.

## 5. Phases

Each phase delivers value on its own and doesn't depend on the next one.

### Phase 1 — MIDI/VGM exporter (Enhanced Synth tap)

*The cheapest and most unique piece in the market.*

- **F1.1** Export VGM v1.71+ with GD3 tags (chiptune community/vgmrips standards —
  see 4.1): raw log of per-chip register writes. NES, GB, SMS (PSG + YM2413).
- **F1.2** Export MIDI (SMF type 1 + General MIDI — see 4.1): reuse the
  note/voice abstractions from `EnhancedSynthEngine` (note-on/off, pitch, channel → MIDI track;
  map synth voices → approximate GM programs based on the active preset).
- **F1.3** UI: "Record music (MIDI/VGM)" action in the audio menu; records while you play.
- **Success criterion:** MIDI of a Mega Man 3 song opens in MuseScore with
  tracks separated by channel and correct notes.

### Phase 2 — Generalize the HD Pack Builder (GB / SMS)

- **F2.1** Port the `HdBuilderPpu` pattern (tile recording during gameplay) to the
  GB and SMS PPUs (both tile-based).
- **F2.2** Organized dump: PNGs sheeted by bank/palette + `hires.txt` compatible with
  the existing HDNes format, extended per proposal 4.2.3 (backward-compatible via
  the `<ver>` field).
- **Success criterion:** running a GB game for 10 min generates a skeleton pack that,
  when reinstalled, renders identical to the original (neutral 1:1 replacement).

### Phase 3 — Unified pack format

- **F3.1** Implement the **MEP v1** spec (4.2.2): `pack.json` with No-Intro hash(es) of the
  ROM, version, author, license, and optional sections `textures/` (hires.txt), `audio/`
  (OGG via OggMixer on NES), `synth/` (embedded ESP preset).
- **F3.2** Granular toggles: each section — and each voice/layer within it —
  individually toggleable in the UI (SUPER ZSNES lesson: "to suit your play style").
- **F3.3** Loading by hash when opening the ROM; multiple packs with precedence.
- **Success criterion:** a single .zip bundles textures + OGG soundtrack + synth preset
  for a game, with each piece separately toggleable.

### Phase 4 — Pack browser in the UI + official channel

- **F4.1** Remote manifest in the **MEI v1** format (4.2.4), hosted in a GitHub repo:
  list of clean packs (presets/mappings/CC originals) with name, game, No-Intro
  hash, URL, checksum, and download counts.
- **F4.2** Discovery UI: list, install, update; ranked by GitHub
  download counts/stars (no in-house telemetry).
- **F4.3** Manifest URLs **configurable by the user** (the default points only to the
  clean official repo; the community can maintain its own indexes in a separate org).
- **F4.4** Contribution = PR to the index repo (curation via review).
- **Success criterion:** installing an Enhanced Audio preset for After Burner in
  2 clicks from the UI, without leaving the emulator.

### Phase 5 — Offline AI pipeline

*External tools (scripts), never embedded in the emulator.*

- **F5.1** Tile upscaling: batch ESRGAN (models trained for pixel art) over the
  Phase 2 dump → 4x draft pack for manual refinement by the community.
- **F5.2** Assisted preset tuning: use the ear-tuning template
  (`docs/EnhancedAudioPresets.example.cfg`) as a prompt — the LLM receives a dump of
  registers/VGM and proposes voice parameters for human review.
- **F5.3** (exploratory) Selection/generation of instrument samples for synth voices.
- **Success criterion:** from game load to a publishable draft pack in < 1h of
  human work.

> **Addendum (2026-08-25).** Phase 5 was re-scoped in
> `docs/roadmap/plano-execucao-F5.md` as *convention-based bootstrap* (a folder next to the
> ROM = the pack, `auto/` = machine, outside it = human; ADR-0049) — the "how" lives there,
> this PRD remains the "why". On the audio side, the ladder ended up: **automatic level 2** =
> real-time GM cover from APU state (per-window channel role, separated SFX,
> arpeggio→chord, SoundFont — F5.4g/ADR-0052), which is what every user
> hears on the first load of any ROM; **3a** = tracks identified by the machine
> (fingerprint + seed MIDI, by playing or by driving the game's sound driver —
> F5.3/F5.4f/ADR-0051), which only feeds **3b** = human orchestration
> (`audio/bgm/<track>.ogg`, swapped in at the right moment by the host). The F5.1–F5.3
> items above (ESRGAN, LLM for presets, samples) remain valid as optional
> external tools on top of this bootstrap.

## 6. Risks and mitigations

| Risk | Prob. | Mitigation |
|---|---|---|
| Takedown of the index repo | low | Index contains only clean content (principle 2); derivatives live in external hubs |
| Project framed as a facilitator (Yuzu pattern) | low | Non-goals: no P2P, no hosting derivatives, no monetization; content-agnostic emulator |
| SUPER ZSNES format becoming a compatibility target | — | Decided: **not pursuing it** — closed format, still in flux, coupled to their renderer |
| Scope exploding (becoming a "second product") | high | Independent phases; F4 uses GitHub as the backend, no dedicated server |
| Small community (personal fork) | medium | Each phase is useful solo for the author; F1 (MIDI export) has appeal beyond the fork |
| New specs not being adopted by third parties | medium | Specs are CC0, federated, and thin (MEP/MEI only compose existing standards); ESP is useful even if only within MesenCE |

## 7. References

- SUPER ZSNES — https://www.zsnes.com/ (curation model and legal data claim)
- Zeldix (MSU-1 hub, other emulators) — https://www.zeldix.net/
- VGMusic (MIDIs since 1996) — https://www.vgmusic.com/
- romhack.ing / RetroGameTalk (RHDN successors); RHDN archive on the Internet Archive
- VGM format + GD3 tags — https://vgmrips.net/ · HD Pack format (hires.txt) — Mesen docs
- No-Intro (Logiqx XML DATs) — https://no-intro.org/ · rcheevos `rhash` — https://github.com/RetroAchievements/rcheevos
- BPS patch format — beat spec (byuu/Near) · MSU-1 — bsnes spec
- Precedents: *MGM v. Grokster* (2005); Yuzu/Nintendo settlement (2024)
