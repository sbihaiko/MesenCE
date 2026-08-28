<div align="center">

# MesenCE · Bihaiko's Edition
[![Build](https://github.com/sbihaiko/MesenCE/actions/workflows/build.yml/badge.svg)](https://github.com/sbihaiko/MesenCE/actions/workflows/build.yml?query=branch%3Amain)
[![Unit tests](https://github.com/sbihaiko/MesenCE/actions/workflows/unit-tests.yml/badge.svg)](https://github.com/sbihaiko/MesenCE/actions/workflows/unit-tests.yml?query=branch%3Amain)
[![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue.svg)](http://www.gnu.org/licenses/gpl-3.0.en.html)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux%20%7C%20macOS-555.svg)](#download)
[![Systems](https://img.shields.io/badge/systems-NES%20%7C%20GB%2FGBC%20%7C%20SMS%2FGG%2FSG--1000%20%7C%20GBA-8a2be2.svg)](#what-it-runs)
[![Specs: CC0](https://img.shields.io/badge/open%20specs-CC0-lightgrey.svg)](docs/specs/)

**[⬇ Download](#download)** · [Hear it](#hear-it) · [See it](#see-it) · [Features](#what-you-get) · [Quick start](#quick-start) · [Packs](#enhancement-packs-mep) · [Why this fork](#why-this-fork) · [FAQ](#faq)<br/>

</div>

## The 30-second pitch — Your NES, Game Boy, Master System, and GBA games, enhanced

**HD art and modern instruments, seamlessly integrated into a single enhancement pack.**  
Everything works automatically, right out of the box — and the enhancements are **on by default**.  
Most emulators stop at *faithful*. **This one starts there and keeps going.**

- **Every game sounds better the moment you load it.** [Enhanced Audio](#enhanced-audio) reads the sound chip's live registers and re-voices them with modern instruments in real time — same notes, same timing, no per-game files required. It just works, and it ships **on**.
- **HD art across three console families, not just one.** Mesen's proven NES HD Pack pipeline now extends to **Game Boy and Master System**. And when no pack exists yet, the emulator can start **building one for you** — automatically upscaling tiles and extracting music from the first time you play.
- **One pack format ties it all together.** Textures, music, and synth presets live in a single hash-matched [MEP](#enhancement-packs-mep) pack. Drop it into a folder and the emulator finds it automatically. Every enhancement layer can still be toggled independently.
- **Built to stay reliable.** Unit tests gate every push — not just *"it compiled."*

Underneath it all is [MesenCE](https://github.com/nesdev-org/MesenCE) / [Mesen2](https://github.com/SourMesen/Mesen2), so you keep Mesen's accuracy, debugger, netplay, shaders, run-ahead, and rewind.

**This fork keeps the emulation faithful — then adds an enhancement layer on top.**

## Download

Fresh builds from the latest `main` — no install, unzip and run:

| Platform | Build | Notes |
|---|---|---|
| **Windows** | [Download](https://nightly.link/sbihaiko/MesenCE/workflows/build/main/Mesen%20%28Windows%20-%20net10.0%20-%20AoT%29.zip) | Windows 7 SP1 or newer |
| **Linux x64** | [Download](https://nightly.link/sbihaiko/MesenCE/workflows/build/main/Mesen%20%28Linux%20-%20ubuntu-22.04%20-%20clang_aot%29.zip) | requires **SDL2** |
| **Linux ARM64** | [Download](https://nightly.link/sbihaiko/MesenCE/workflows/build/main/Mesen%20%28Linux%20-%20ubuntu-22.04-arm%20-%20clang_aot%29.zip) | requires **SDL2** |
| **macOS Apple Silicon** | [Download](https://nightly.link/sbihaiko/MesenCE/workflows/build/main/Mesen%20%28macOS%20-%20macos-15%20-%20clang_aot%29.zip) | requires **SDL2**; self-signed — allow it once in Gatekeeper |
| **macOS Intel** | [Download](https://nightly.link/sbihaiko/MesenCE/workflows/build/main/Mesen%20%28macOS%20-%20macos-15-intel%20-%20clang_aot%29.zip) | requires **SDL2**; self-signed — allow it once in Gatekeeper |

Per-commit builds live in the [Actions](https://github.com/sbihaiko/MesenCE/actions/workflows/build.yml?query=branch%3Amain) tab. Building from source: [COMPILING.md](COMPILING.md).

## Hear it

*Mega Man 3, Shadow Man stage. Same game, same notes, same timing — only the instruments change.*

| | |
|---|---|
| **Before** — original NES chip (2A03) | ▶ [shadowman-before.mp3](https://raw.githubusercontent.com/sbihaiko/MesenCE/main/docs/media/shadowman-before.mp3) |
| **After** — Enhanced Audio, **Studio** style | ▶ [shadowman-enhanced.mp3](https://raw.githubusercontent.com/sbihaiko/MesenCE/main/docs/media/shadowman-enhanced.mp3) |

![Spectrogram: original NES chip audio vs. Enhanced Audio remaster](docs/media/shadowman-spectrogram.png)

Melody and timing come straight from the game's own APU register log. Enhanced Audio never re-composes — it re-*voices*: the square-wave lead becomes a detuned-saw lead, the mix gains body, and every note stays exactly where the game put it. More demos (Game Boy, SMS FM) will land here as presets get ear-tuned.

## See it

Enhanced Audio is the sound half. The visual half is what the HD-pack community already achieves on NES with the same engine this fork ships:

<!-- Images hotlinked from the pack author's own repository, with credit — not redistributed here. -->
<p align="center">
  <a href="https://github.com/TasticHacks/Contra80s"><img src="https://raw.githubusercontent.com/TasticHacks/Contra80s/main/screenshots/Contra80s-Screenshot-Larger-1.png" width="49%" alt="Contra 80s — NES Contra rendered with full HD textures via a Mesen HD Pack"></a>
  <a href="https://github.com/TasticHacks/Contra80s"><img src="https://raw.githubusercontent.com/TasticHacks/Contra80s/main/screenshots/Contra80s-Screenshot-Larger-4.png" width="49%" alt="Contra 80s — HD pack gameplay, jungle stage reimagined"></a>
</p>

<p align="center"><sub><i>Contra</i> (NES, 1988) through <b><a href="https://github.com/TasticHacks/Contra80s">Contra 80s</a></b>, an HD pack by <b>Tastic</b> — 8-bit graphics replaced in real time with hand-made HD art (<a href="https://www.youtube.com/watch?v=Ho1-30w41RU">trailer</a>). More packs: <a href="https://github.com/lyonhrt/hdnes-projects">lyonhrt</a> · <a href="https://forums.nesdev.org/viewtopic.php?t=17110">NESDev thread</a>.</sub></p>

This fork takes that pipeline to **Game Boy and Master System**, bundles it with Enhanced Audio in one pack format, and makes packs discoverable from inside the emulator.

## What you get

| | Stock Mesen / MesenCE | **This fork** |
|---|---|---|
| **Audio** | Faithful chip emulation | Faithful emulation **+ real-time modern re-synthesis**, on by default, 5 styles, optional General MIDI SoundFont, tunable via a text file |
| **HD textures** | NES only | **NES, Game Boy/GBC, SMS/Game Gear/SG-1000** |
| **Starter packs** | Hand-authored from a blank canvas | **Auto-bootstrapped** beside the ROM: xBRZ-upscaled tiles, static screens, extracted music |
| **Pack format** | `hires.txt` per game | **MEP**: one hash-keyed pack for textures + audio + synth presets, folder or `.zip`, per-layer toggles |
| **Music export** | — | **Record Music (MIDI/VGM)** while you play |
| **Correctness** | Build check | **CI-gated unit tests** on every push |
| **Consoles** | 10+ systems | **4 families**, chosen because their enhancement ecosystems already exist ([why](#why-this-fork)) |

### What it runs

**NES / Famicom** · **Game Boy / Game Boy Color / GBS** · **Master System / Game Gear / SG-1000** (incl. YM2413 FM) · **Game Boy Advance**

Not included: SNES (incl. Super Game Boy), PC Engine, WonderSwan, ColecoVision — see [FAQ](#faq).

## Quick start

1. **[Download](#download)**, unzip, run `Mesen`.
2. **File → Open** a ROM. Enhanced Audio is already on (Style: *Studio*).
3. Want it different? **Settings → Audio → General → "Enhanced audio (experimental)"** — toggle, pick a style (Synthwave, Chip Deluxe, Orchestral Lite, Dry, Studio), balance synth vs. original chip.
4. Got an HD pack or MEP pack? Drop the folder or `.zip` into `EnhancementPacks/` (or a folder named like the ROM, beside it) and open **Tools → HD Packs → Enhancement Packs (MEP)…** to toggle textures / audio / synth per pack.
5. Want a MIDI or VGM of the soundtrack? **Tools → Record Music (MIDI/VGM)** while the game plays.

## Enhanced Audio

An alternative synthesizer that reads the **live chip state** — frequency, volume, duty, key-on — and re-voices it with modern instruments in real time, on any ROM, with zero per-game assets. The original chip stays the source of truth; the synth mixes on top of (or replaces) its output.

- **Supported cores:** NES (2A03), Game Boy/GBC APU, SMS-family (SN76489 PSG **and** YM2413 FM — *After Burner*, *Shadow Dancer* and other FM soundtracks are covered, with FM rhythm mode mapped to drum voices). On GBA the checkbox is visible but has no effect yet.
- **Smart voicing:** a channel-role classifier separates melody, bass and SFX so sound effects don't get orchestrated along with the music.
- **Styles:** Synthwave, Chip Deluxe, Orchestral Lite, Dry, Studio — each console has its own tuning on a shared DSP engine.
- **Bring your own instruments:** point it at any General MIDI **SoundFont (.sf2)** (Settings → Audio) or drop `EnhancedAudio.sf2` in the Mesen folder.
- **Tune without recompiling:** `EnhancedAudioPresets.cfg` in the Mesen home folder, with `[Studio]`, `[Studio.Gb]`, `[Studio.Sms]` sections. Documented template: [docs/EnhancedAudioPresets.example.cfg](docs/EnhancedAudioPresets.example.cfg). Format spec: [ESP v1](docs/specs/ESP-v1.md).
- Per-console channel volumes apply to the synth voices too — muting a chip channel mutes its enhanced voice.

## Enhancement Packs (MEP)

Textures, music and synth presets ship as **one hash-keyed pack**, matched to your ROM by its No-Intro hash — no per-game config.

- **Install:** a folder or `.zip` in `EnhancementPacks/`, or a folder named like the ROM right beside it (the sibling folder always wins).
- **Toggle per layer:** textures / audio (OGG) / synth / ROM patches, from **Tools → HD Packs → Enhancement Packs (MEP)…**.
- **Never start from nothing:** with *Bootstrap* on, playing a game with no pack writes `<Game>/auto/` beside the ROM — xBRZ 4× tiles, static screens as backgrounds and (NES) fingerprinted music ready for `scripts/mep_render_audio.py`. An artist gets a real starting point; a player gets something better than raw pixels immediately.
- **Built on existing standards** (No-Intro hashes, HDNes `hires.txt`, VGM/GD3, SMF/GM, OGG, BPS) — and where a gap exists, small **CC0 specs anyone can implement**: [MEP v1](docs/specs/MEP-v1.md) (pack) · [ESP v1](docs/specs/ESP-v1.md) (presets) · [MEI v1](docs/specs/MEI-v1.md) (federated discovery) · [hires.txt GB/SMS](docs/specs/hires-gbsms-v1-draft.md) (draft).
- **Tooling:** `scripts/mep_lint.py` validates a pack offline; **Tools → HD Packs → HD Pack Builder** records tiles while you play.

Current limits: the `audio` layer is applied on NES only (GB/SMS wait for the hires.txt extension to freeze). Roadmap and design notes: [docs/enhancement-ecosystem.md](docs/enhancement-ecosystem.md).

**Legal footing:** the project ships tools, mappings and specs — never other people's game assets. Extraction happens on your machine and stays there.

## Built to stay correct

Every push and PR runs [`unit-tests.yml`](.github/workflows/unit-tests.yml) in addition to the native build:

- **`core-unit-tests`** — dependency-free C++ harness (`scripts/core_unit_tests.cpp`, `make core-unit-tests`) for core logic: Enhanced Audio channel-role classifier, MEP parsing, and other logic deliberately factored out so it can be tested without a ROM or GUI.
- **`UI.Tests`** — C# xUnit suite (`UI.Tests/`) for the host layer: cheat parsing, pack-list handling, MEP parser and zip validator.

No SDL2, no full core, results in seconds. It's not full-core coverage — it's real, growing coverage of what this fork adds and changes, so regressions get caught before they ship.

## Why this fork

**Focused, not generalist.** Every console a multi-system emulator carries is another core to keep accurate, another regression surface, another place "enhancement" has to be reinvented. Dropping SNES, PCE, WonderSwan and ColecoVision freed the effort for three things a generalist can't easily have: audio that upgrades every game automatically, a shared pack format across consoles, and a real test layer. The four remaining families are exactly the ones where community HD packs and music extraction already prove the concept.

**Built with AI, on purpose.** Implementation, review and the test suite are AI-assisted. That's what lets a small project move four cores, a synth engine and a pack ecosystem forward at once — with tests, not manual review alone, as the safety net. It's also why this is an independent fork: upstream's contribution policy doesn't accept AI-assisted PRs (Enhanced Audio was proposed as [PR #262](https://github.com/nesdev-org/MesenCE/pull/262) and closed for exactly that reason). Design decisions are recorded as an [ADR trail](.dev-squad/adr/), so the *why* stays reviewable. Upstream accuracy fixes from MesenCE/Mesen2 are ported in regularly, so enhancement doesn't mean drifting from accuracy.

## FAQ

**Where's SNES?** Not here, deliberately. [bsnes](https://github.com/bsnes-emu/bsnes), [snes9x](https://github.com/snes9x/snes9x) and [ZSNES](https://www.zsnes.com/) already do it better than a bolted-on core would.

**Does Enhanced Audio change the music?** No. It changes the *instruments*. Notes, timing and dynamics come from the game's own registers, frame by frame.

**Can I turn it all off?** Yes — one checkbox in Settings → Audio, and you have stock Mesen accuracy.

**Do existing NES HD packs work?** Yes, the HDNes `hires.txt` format is unchanged; drop them in `HdPacks/` as always, or wrap them in a MEP pack.

**Will you host packs?** No. The emulator can consume any [MEI](docs/specs/MEI-v1.md) index; packs stay with their authors and the existing community hubs.

## Contributing & community

- **Found a game that sounds wrong / a pack that doesn't load?** [Open an issue](https://github.com/sbihaiko/MesenCE/issues) with the ROM's No-Intro name — never the ROM.
- **Made a pack?** Publish it in your own repo and open an issue so it can be listed.
- **Tuned a style by ear?** Presets are just `.cfg` files — PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits & license

Built on [Mesen2](https://github.com/SourMesen/Mesen2) by Sour and [MesenCE](https://github.com/nesdev-org/MesenCE) by the nesdev.org community. GPL v3 — full text: <http://www.gnu.org/licenses/gpl-3.0.en.html>. Copyright (C) 2014-2026 Sour, 2026 contributors. Open specs in `docs/specs/` are CC0.
