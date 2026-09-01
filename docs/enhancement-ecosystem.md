# MesenCE Community Enhancement Ecosystem

*Status: draft / roadmap — the consolidated PRD (Part A: pack/core; Part B:
player GUI) at
[docs/roadmap/PRD-mesence-enhancement-ecosystem.md](roadmap/PRD-mesence-enhancement-ecosystem.md).*

Enhanced Audio is step one of a larger plan: turning MesenCE into a platform for
**extracting, authoring and consuming community enhancement packs** — textures, music
and synth presets — while keeping the emulator itself legally clean.

The thesis is proven: the relaunched [SUPER ZSNES](https://www.zsnes.com/) built its
whole product around per-game curated enhancements (hand-drawn hi-res art, audio
replacement, overclock), each individually toggleable, with enhancement data kept free
of copyrighted content. MesenCE already ships the three foundations needed to do the
same as an open ecosystem:

| Foundation | Where | What it provides |
|---|---|---|
| NES HD Packs (HDNes format) | `Core/NES/HdPacks/` | Tile + OGG audio replacement, per-context conditions, and the **HD Pack Builder** (in-emulator tile recorder) |
| MSU-1 | not on `main` — `Core/SNES/` is an empty skeleton (no tracked files); see [`docs/roadmap/PRD-mesence-enhancement-ecosystem.md`](roadmap/PRD-mesence-enhancement-ecosystem.md) for the product scope (SNES/MSU-1 is out of scope, ADR-0041) | The open SNES streaming-audio standard, kept here as a design reference only |
| Enhanced Synth Engine | `Core/Shared/Audio/EnhancedSynthEngine.*` | A live tap that already converts chip register state into note/voice abstractions — most of a MIDI exporter |

## Principles

1. **Ship the tool, never the content.** Extractors are legal (interoperability);
   their outputs stay on the user's machine. Extracted tiles and transcribed music are
   still copyrighted works (a MIDI of a game tune is a transcription of the
   composition, like sheet music — changing format never clears the musical work).
2. **The official channel carries only clean data:** synth presets, ROM-hash mappings,
   index manifests, tools, and original compositions with explicit licenses. One
   deliberate exception: short before/after demonstration excerpts and gameplay
   screenshots in `docs/media/` — the same de facto practice every emulator's
   documentation relies on — kept brief, credited where a community author is
   involved, and never full tracks or complete asset sets.
3. **Derivative content lives in the existing community hubs** (Zeldix for SNES audio
   packs, VGMusic for MIDI, romhack.ing / individual GitHub repos for texture packs) —
   the same separation bsnes keeps from the MSU-1 pack sites.
4. **The emulator is content-agnostic.** It consumes user-configurable index URLs; it
   never bundles, hosts, endorses, or embeds any P2P distribution of derivative
   content (inducement liability — *MGM v. Grokster*, 2005; the 2024 Yuzu settlement).

## Standards

Rule of thumb: **adopt an existing community standard wherever one exists; formalize a
small open spec only where none does.**

### Adopted standards

| Area | Standard | Used for | Why |
|---|---|---|---|
| ROM identification | No-Intro (Logiqx XML DATs, CRC32/MD5/SHA-1) | Pack and index keys | Interop with RetroArch, collection managers, existing databases |
| Per-system hashing | rcheevos `rhash` | Systems that hash only part of the file | Future RetroAchievements compatibility |
| Audio register logs | VGM v1.71+ with GD3 tags | Music exporter | Plays in any VGM player (foobar2000, in_vgm); vgmrips-standard metadata |
| Note data | SMF type 1 + General MIDI | Music exporter | Opens in MuseScore / any DAW, no conversion |
| Textures | HDNes `hires.txt` (Mesen is the reference implementation) | Texture packs | Existing pack authors and tools already speak it |
| SNES audio | MSU-1 (`.msu` + `.pcm`) | Audio replacement | A decade of Zeldix packs work on day zero |
| NES audio | OGG via HD pack (`OggMixer`) | Audio replacement | Already supported; part of the HDNes standard |
| ROM patches | BPS (beat) | If packs ever include patches | Validates the source ROM checksum — fits the hash-keyed model |

The one real gap: replacement audio for **GB/SMS** (MSU-MD only covers the Mega
Drive). It is addressed by the hires.txt extension proposal below.

### New open specs (proposed)

Each spec will live in `docs/specs/<id>-v<N>.md`, licensed **CC0** (public domain —
any emulator may implement it), written with RFC 2119 normative language
(MUST/SHOULD/MAY), semver versioning, canonical example files ("golden files") and a
validation script. Changes go through issues/PRs; breaking changes bump the major
version.

| Spec | Defines |
|---|---|
| **ESP v1** — Enhanced Synth Preset | The `EnhancedAudioPresets.cfg` format: file grammar, per-chip voice parameters (NES APU, GB APU, SMS PSG, YM2413), valid ranges, defaults for omitted fields, and the per-game → per-chip → global fallback rules. The only 100%-new format in the ecosystem. |
| **MEP v1** — Enhancement Pack | A thin `.zip` envelope with `pack.json` at the root that only *composes* existing standards: No-Intro hash key, metadata (name, author, license, semver), and optional sections — `textures/` (hires.txt), `audio/` (OGG / MSU-1), `synth/` (ESP). Every section is individually toggleable. |
| **MEI v1** — Enhancement Index | The federated pack-discovery manifest: a `manifest.json` listing packs (name, game, No-Intro hash, URL, artifact checksum, license). Anyone can publish an index; users point the emulator at any of them — the official index is just one MEI among others. |
| **hires.txt GB/SMS extension** | A backward-compatible extension of the HDNes format via its existing `<ver>` field: new tags for the GB/SMS PPUs (CGB palettes, VDP modes) and OGG audio replacement on those systems. To be discussed with the HDNes/Mesen community before freezing v1. |

## Roadmap phases

Five self-contained phases — each delivers value on its own (details, requirements and
success criteria in the [PRD](roadmap/PRD-mesence-enhancement-ecosystem.md)):

1. **MIDI/VGM music exporter** built on the Enhanced Synth tap — record a game's music
   to VGM (+GD3) or MIDI (SMF/GM) while playing.
2. **HD Pack Builder generalized** to Game Boy and SMS (both tile-based PPUs).
3. **Unified enhancement pack format** (MEP): textures + audio + synth preset in one
   hash-keyed archive, every layer individually toggleable.
4. **In-UI pack browser** consuming federated MEI indexes (GitHub-backed, no custom
   server, ranking via download counts).
5. **Offline AI pipeline** (external scripts, never embedded): ESRGAN-family tile
   upscaling and LLM-assisted preset ear-tuning to produce first-draft packs for the
   community to refine by hand.

## Non-goals

- Hosting or distributing derivative content (extracted MIDIs, covers, redrawn
  third-party textures) in any project repository.
- Any embedded P2P/torrent sharing mechanism.
- Monetizing packs or the distribution channel.
- Compatibility with the closed SUPER ZSNES enhancement data format.
