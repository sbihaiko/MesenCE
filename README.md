# MesenCE — sbihaiko's fork

A personal fork of [MesenCE](https://github.com/nesdev-org/MesenCE) (itself a fork of [Mesen](https://github.com/SourMesen/Mesen2)), a multi-system emulator for Windows, Linux, and macOS covering NES, SNES, Game Boy (GB/SGB/GBC), Game Boy Advance, PC Engine, SMS/Game Gear, and WonderSwan (WS/WSC).

**Why this fork exists:** to grow the emulator into an open platform for **community game enhancements** — modern-timbre audio, HD textures, music extraction, and shareable enhancement packs — built on open standards, with the emulator staying legally clean: it ships **tools, never content**. The charter lives in the [Community Enhancement Ecosystem](docs/enhancement-ecosystem.md) document; **Enhanced Audio** is phase one, already shipped and on by default.

## 🎧 Hear it — before / after

*Mega Man 3, Shadow Man stage. Same game, same notes, same timing — only the instruments change.*

| | |
|---|---|
| **Before** — original NES chip (2A03) | ▶ [shadowman-before.mp3](https://raw.githubusercontent.com/sbihaiko/MesenCE/main/docs/media/shadowman-before.mp3) |
| **After** — Enhanced Audio, **Studio** style | ▶ [shadowman-enhanced.mp3](https://raw.githubusercontent.com/sbihaiko/MesenCE/main/docs/media/shadowman-enhanced.mp3) |

Melody and timing come straight from the game's own APU register log — the *after* track is the reference mix the built-in **Studio** style is a verbatim port of. Enhanced Audio never re-composes; it re-*voices*: listen for the square-wave lead becoming a detuned-saw lead and the whole mix gaining body while every note stays exactly where the game put it.

![Spectrogram: original NES chip audio vs. resynthesized mix vs. Enhanced Audio remaster](docs/media/shadowman-spectrogram.png)

*Same passage, three renderings: the thin harmonic lines of the raw 2A03 versus the full-spectrum enhanced mix. More before/after demos (Game Boy, SMS FM) will land here as presets get ear-tuned.*

## 🖼 See it — where this is going

Enhanced Audio is the sound half of the story. The visual half already exists on NES through Mesen's HD pack pipeline — this is the level of transformation the community reaches today, on the same engine this fork ships:

<!-- Images hotlinked from the pack author's own repository, with credit — not redistributed here.
     TODO: replace with our own same-frame before/after captures (original vs. HD pack) once recorded. -->
<p>
  <a href="https://github.com/TasticHacks/Contra80s"><img src="https://raw.githubusercontent.com/TasticHacks/Contra80s/main/screenshots/Contra80s-Screenshot-Larger-1.png" width="49%" alt="Contra 80s — NES Contra rendered with full HD textures via a Mesen HD Pack"></a>
  <a href="https://github.com/TasticHacks/Contra80s"><img src="https://raw.githubusercontent.com/TasticHacks/Contra80s/main/screenshots/Contra80s-Screenshot-Larger-4.png" width="49%" alt="Contra 80s — HD pack gameplay, jungle stage reimagined"></a>
</p>

*Contra (NES, 1988) running through **[Contra 80s](https://github.com/TasticHacks/Contra80s)**, an HD pack by **Tastic** — original 8-bit graphics replaced in real time with hand-made HD art ([launch trailer](https://www.youtube.com/watch?v=Ho1-30w41RU) shows the before/after in motion). More community packs: [lyonhrt's projects](https://github.com/lyonhrt/hdnes-projects) · [NESDev HD pack thread](https://forums.nesdev.org/viewtopic.php?t=17110).*

Where this fork takes it (the [ecosystem roadmap](docs/enhancement-ecosystem.md)): the same authoring pipeline extended to **Game Boy and SMS**, unified with Enhanced Audio in a single hash-keyed pack format, discoverable from inside the emulator — every layer individually toggleable.

## Enhanced Audio (NES, Game Boy, SMS, Game Gear, SG-1000)

This fork adds an experimental **Enhanced Audio** mode for the NES (2A03 APU), Game Boy (GB/GBC APU, handheld mode — not SGB) and SMS-family (SN76489 PSG, shared by SMS, Game Gear, SG-1000) cores: an alternative synthesizer that reinterprets the live chip channel state (frequency, volume, and duty on the NES) with modern instrument timbres in real time, on any ROM, with zero per-game assets. The original chip stays the source of truth — the synth only reads its state and mixes on top of (or replaces) the original chip output. **It's on by default** (Style: Studio). Since the setting applies across every supported console, it lives in one place: **Settings → Audio → General tab → "Enhanced audio (experimental)"**, where you can toggle it, pick a Style, and adjust the synth volume and original chip mix. Each console runs its own synth mapping and its own set of built-in styles tuned for that chip (on top of one shared DSP engine), but they share this single on/off switch. **Only the NES, Game Boy and SMS-family cores actually implement it** — on every other console (SNES, GBA, PC Engine, WonderSwan), and on Game Boy games running through the Super Game Boy, the checkbox is visible but has no effect. The per-console *channel volume* settings (e.g. Settings → NES/SMS → Audio) apply to the synth voices as well — muting a chip channel also mutes its enhanced voice.

On SMS-family titles that switch their soundtrack over to the optional YM2413 FM add-on (e.g. *After Burner*, *Shadow Dancer*) and mute the PSG entirely, the SMS engine also reinterprets the FM chip's own live register state (frequency, volume, key-on, up to 9 simultaneous notes) so those games get enhanced music too, not just PSG-only titles like *Fantasy Zone*. When a game mutes the PSG through the audio control port, the synth stops reinterpreting the PSG registers as well, so stale notes/noise never play under the FM voices. FM's rhythm/percussion mode is mapped onto the synth's drum voice (bass drum/tom as drum body and low thump, snare/cymbal/hi-hat as the bright top), rather than emulated.

Five built-in styles are included per engine: Synthwave, Chip Deluxe, Orchestral Lite, Dry, and Studio (a port of an offline remaster mix, with a fixed detuned-saw lead and a light bus compressor). Every instrument parameter can also be tuned without recompiling, via an `EnhancedAudioPresets.cfg` file placed in the Mesen home folder — the NES engine reads sections like `[Studio]`, the Game Boy engine `[Studio.Gb]`, and the SMS-family engine `[Studio.Sms]`, so each can be tuned independently from the same file. Edits to the file are picked up on console reset / ROM load (the file is never read from the audio path). A fully documented template with every field and the built-in defaults is included at [docs/EnhancedAudioPresets.example.cfg](docs/EnhancedAudioPresets.example.cfg) — the SMS and Game Boy tunings are inherited from the NES engine and still need ear-calibration, so that's the place to start.

This feature was originally proposed upstream as [PR #262](https://github.com/nesdev-org/MesenCE/pull/262). It was built with the help of AI tools, which the upstream project's contribution policy does not allow, so the PR was closed and this work now lives here instead, for personal use.

## Community Enhancement Ecosystem (roadmap)

These definitions are the fork's charter — the reason it exists beyond any single feature. The plan grows Enhanced Audio into an open enhancement ecosystem, in five self-contained phases:

1. **MIDI/VGM music exporter** — record a game's music to VGM (+GD3 tags) or MIDI (SMF/GM) while playing, built on the Enhanced Synth tap. ✅ **Done** (NES, GB, SMS — PSG + YM2413).
2. **HD Pack Builder generalized** to Game Boy and SMS. ✅ **Done** — the full record → edit → replace loop works for GB/GBC and SMS/GG: tile capture and hires.txt `<ver>200` dumps (tile identity keys recorded as ADR-0036/0037), plus the in-emulator pack loader/renderer and the HD Packs menu for both consoles. A neutral recorded pack re-renders pixel-identical when reinstalled (validated headless on DMG, CGB and SMS). SMS coverage is VDP mode 4 (SG-1000 legacy modes excluded from v1); re-recording merges into an existing pack, and **Export ROM Tiles** writes every bitmap found in the ROM (whole CHR ROM on NES; uncompressed tiles on GB/SMS) as palette-agnostic `defaultTile` entries without playing (ADR-0043).
3. **Unified enhancement pack format** — textures + audio + synth preset in one hash-keyed archive, every layer individually toggleable. ✅ **Done** — the MEP v1 host is in: packs live in `EnhancementPacks/` (folder or `.zip`), are matched by No-Intro SHA-1 computed from the ROM file, and their `textures` (NES/GB/SMS hires.txt), `audio` (NES OGG via `<bgm>`/`<sfx>`) and `synth` (ESP preset layered below the user's file) sections are delegated to the existing loaders, with a loose `HdPacks/` pack always winning textures. The *HD Packs › Enhancement Packs* window lists matching packs with a checkbox per pack and per layer and installs `.zip` packs. Decisions in ADR-0038…0042; host limitations (audio is NES-only until the GB/SMS extension freezes) documented in `docs/specs/README.md`.
4. **In-UI pack browser** consuming federated indexes (GitHub-backed, no custom server).
5. **Automatic pack bootstrap** (convention over configuration) — playing a game creates a sibling folder next to the ROM, with the ROM's name, holding auto-optimised textures (tile upscaling) and audio (per-track MIDI → rendered OGG, triggered without ROM patches via APU fingerprints); everything under `auto/` is regenerable, everything outside it is the artist's. That folder *is* the pack and the artist's starting point. 🚧 **In progress** — the host side is in (F5.1): a folder or `.zip` named like the ROM beside it or in `EnhancementPacks/` loads with no `pack.json`, the sibling folder outranks any installed pack, `auto/` is merged under the human layer per tile, packs can ship `patches[]` per ROM revision (dumps with trailing garbage now hash like their clean No-Intro entry), and `scripts/mep_lint.py` validates packs offline. The first automatic layer is live too (F5.2): when no pack dresses a game yet, playing it records every drawn tile upscaled with xBRZ 4× (plus the whole CHR ROM on NES) into `<Game>/auto/textures/` beside the ROM — the next load already uses it, and *HD Packs › Enhancement Packs › Open Game Folder* opens the artist's workspace. Music follows the same path (F5.3): on NES the bootstrap also records what the APU plays into `<Game>/auto/audio/` — one General MIDI file per track plus `fingerprints.json` — `scripts/mep_render_audio.py` renders them to `bgm/<id>.ogg` (fluidsynth + SoundFont, or a built-in chip synth), and on the next load the host recognises each track from its first notes and swaps in the OGG while muting the APU's tonal channels — no ROM patch, no `$41xx` hooks (ADR-0047); an artist just drops a better `audio/bgm/<id>.ogg` beside it. Opening a ROM now extracts most of its graphics before you play: CHR ROM games export every tile, and CHR RAM games (Zelda, Castlevania, Mega Man…) get a heuristic scan of the PRG ROM that finds ~80–99 % of the tiles the game will draw; these palette-agnostic gray entries are recolored with the live palette at draw time, so an export-only layer already plays in color. Static screens are captured too (F5.4a): a title or menu that holds still for a moment is saved as `auto/textures/backgrounds/screenNNN.png` — the full frame without sprites, upscaled in one pass — with three `tileAtPosition` anchors and a `<background>` line, the exact format the most elaborate community packs are built from (ADR-0050, decided after measuring the auto layer against Castlevania, Contra80s and Zelda Remastered with `scripts/mep_compare.py`). Next: automatic palette variants, `mep_build.py`, coverage in the UI, object sheets. Plan in [`docs/roadmap/plano-execucao-F5.md`](docs/roadmap/plano-execucao-F5.md) (ADR-0044/0047/0049).

Wherever a community standard already exists we adopt it instead of inventing one: **No-Intro** hashes for ROM identification, **VGM + GD3** for register logs, **SMF/General MIDI** for note data, **HDNes `hires.txt`** for textures, **MSU-1** and **OGG HD-pack audio** for audio replacement, **BPS** for patches. Where none exists, we are formalizing small open specs — **CC0-licensed**, RFC 2119 language, semver, golden files — so any emulator or pack author can adopt them:

| Spec | Defines | Status |
|---|---|---|
| **ESP v1** — Enhanced Synth Preset | The `EnhancedAudioPresets.cfg` format (grammar, per-chip voice parameters, fallback rules) | [Published](docs/specs/ESP-v1.md) |
| **MEP v1** — Enhancement Pack | A thin `.zip` envelope composing existing formats, keyed by No-Intro hash | [Published](docs/specs/MEP-v1.md) |
| **MEI v1** — Enhancement Index | A federated pack-discovery manifest — anyone can publish an index | [Published](docs/specs/MEI-v1.md) |
| **hires.txt GB/SMS extension** | Backward-compatible HDNes extension for GB/SMS tiles and OGG audio | [v1 draft](docs/specs/hires-gbsms-v1-draft.md) — open for community review before freezing |

Ground rule that keeps the project safe: extraction is local, the official channel carries only clean data (presets, mappings, manifests, tools), and derivative content lives in the existing community hubs — the emulator never hosts, bundles, or embeds distribution of it.

📄 Full definitions: [Enhancement Ecosystem](docs/enhancement-ecosystem.md) · [PRD (pt-BR)](docs/roadmap/PRD-ecossistema-enhancement-comunitario.md) · [Preset template](docs/EnhancedAudioPresets.example.cfg)

## Development Builds

[![Mesen](https://github.com/sbihaiko/MesenCE/actions/workflows/build.yml/badge.svg)](https://github.com/sbihaiko/MesenCE/actions/workflows/build.yml?query=branch%3Amain)

* [Windows](https://nightly.link/sbihaiko/MesenCE/workflows/build/main/Mesen%20%28Windows%20-%20net10.0%20-%20AoT%29.zip)
  * Windows 7 or higher is required. Windows 7 users must use SP1 and have all updates installed.
* [Linux x64](https://nightly.link/sbihaiko/MesenCE/workflows/build/main/Mesen%20%28Linux%20-%20ubuntu-22.04%20-%20clang_aot%29.zip)  (requires **SDL2**)  
* [Linux ARM64](https://nightly.link/sbihaiko/MesenCE/workflows/build/main/Mesen%20%28Linux%20-%20ubuntu-22.04-arm%20-%20clang_aot%29.zip)  (requires **SDL2**)  
* [macOS - Intel](https://nightly.link/sbihaiko/MesenCE/workflows/build/main/Mesen%20%28macOS%20-%20macos-15-intel%20-%20clang_aot%29.zip)  (requires **SDL2**)  
* [macOS - Apple Silicon](https://nightly.link/sbihaiko/MesenCE/workflows/build/main/Mesen%20%28macOS%20-%20macos-15%20-%20clang_aot%29.zip)  (requires **SDL2**)  

Other builds (per-commit) are available in the [Actions](https://github.com/sbihaiko/MesenCE/actions/workflows/build.yml?query=branch%3Amain) tab. macOS builds are self-signed and require approval via Gatekeeper before they can run.

## License

Mesen is available under the GPL V3 license.  Full text here: <http://www.gnu.org/licenses/gpl-3.0.en.html>
Copyright (C) 2014-2026 Sour, 2026 contributors
