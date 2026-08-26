# MesenCE — sbihaiko's fork

**A focused emulator, not a checklist of consoles.** A personal fork of [MesenCE](https://github.com/nesdev-org/MesenCE) (itself a fork of [Mesen](https://github.com/SourMesen/Mesen2)) for Windows, Linux, and macOS, covering **NES, Game Boy / Game Boy Color / GBS, Master System / Game Gear / SG-1000, and Game Boy Advance** — the systems where a mature, community-built enhancement ecosystem (HD texture packs, music extraction, chip-accurate register logs) already exists and actually moves the needle. This fork does **not** emulate SNES (including Super Game Boy), PC Engine, WonderSwan, or ColecoVision.

That's deliberate, not a gap. For SNES specifically, dedicated projects like [ZSNES](https://www.zsnes.com/), [snes9x](https://github.com/snes9x/snes9x), and [bsnes](https://github.com/bsnes-emu/bsnes) already do that job better than a bolted-on core in a multi-system emulator ever could. Every console a generalist emulator carries is another core to keep accurate, another surface to regression-test, another place "enhancement" has to be reinvented from scratch. Dropping four systems didn't shrink this project — it freed the effort that used to be spread across ten cores into three things a general-purpose emulator can't easily have: audio that upgrades every game **automatically and on by default**, a **standardized pack format** for textures + audio + presets shared across consoles, and a real **CI-gated test layer** instead of "it compiled, it booted a ROM." Less surface, more depth.

## Why this fork, and not a generalist emulator

| | Generalist multi-system emulators | MesenCE (this fork) |
|---|---|---|
| **Console list** | Broad — often 10+ systems, uneven depth | **4** systems, chosen because their enhancement packs already exist and matter: NES, Game Boy, SMS-family, GBA |
| **Audio** | Faithful chip emulation, full stop | Faithful emulation **+ automatic, on-by-default modern re-synthesis** ([Enhanced Audio](#enhanced-audio-nes-game-boy-sms-game-gear-sg-1000)) — swappable per game, tunable without recompiling |
| **HD art / packs** | Per-project, bespoke pack formats if any | One **standardized, hash-keyed pack format** ([MEP](docs/specs/MEP-v1.md)) unifying textures, audio, and synth presets — with a folder auto-bootstrapped per ROM, no manual authoring required to start |
| **Correctness** | Usually "it compiles, it plays a ROM" | **CI-gated unit tests** on every push — [see below](#built-to-stay-correct) |
| **Development speed** | Slow, contributor- and review-bottlenecked | **AI-accelerated** — [see below](#built-with-ai-on-purpose) — tools ship in days, iterated in the open |

This isn't an attempt at "the best SNES emulator" — that's already solved elsewhere. It's the best **enhancement platform** for the systems where community packs already prove the concept, kept trustworthy by automated tests while it iterates fast.

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

This fork takes that same authoring pipeline and extends it to **Game Boy and SMS**, unifies it with Enhanced Audio in a single hash-keyed pack format ([details below](#enhancement-packs--one-format-not-five)), and makes it discoverable from inside the emulator — every layer individually toggleable, and increasingly generated automatically rather than hand-authored.

## Enhanced Audio (NES, Game Boy, SMS, Game Gear, SG-1000)

This fork adds an experimental **Enhanced Audio** mode for the NES (2A03 APU), Game Boy (GB/GBC APU, handheld) and SMS-family (SN76489 PSG, shared by SMS, Game Gear, SG-1000) cores: an alternative synthesizer that reinterprets the live chip channel state (frequency, volume, and duty on the NES) with modern instrument timbres in real time, on any ROM, with zero per-game assets. The original chip stays the source of truth — the synth only reads its state and mixes on top of (or replaces) the original chip output. **It's on by default** (Style: Studio). Since the setting applies across every supported console, it lives in one place: **Settings → Audio → General tab → "Enhanced audio (experimental)"**, where you can toggle it, pick a Style, and adjust the synth volume and original chip mix. Each console runs its own synth mapping and its own set of built-in styles tuned for that chip (on top of one shared DSP engine), but they share this single on/off switch. **Only the NES, Game Boy and SMS-family cores actually implement it** — on GBA the checkbox is visible but has no effect. The per-console *channel volume* settings (e.g. Settings → NES/SMS → Audio) apply to the synth voices as well — muting a chip channel also mutes its enhanced voice.

On SMS-family titles that switch their soundtrack over to the optional YM2413 FM add-on (e.g. *After Burner*, *Shadow Dancer*) and mute the PSG entirely, the SMS engine also reinterprets the FM chip's own live register state (frequency, volume, key-on, up to 9 simultaneous notes) so those games get enhanced music too, not just PSG-only titles like *Fantasy Zone*. When a game mutes the PSG through the audio control port, the synth stops reinterpreting the PSG registers as well, so stale notes/noise never play under the FM voices. FM's rhythm/percussion mode is mapped onto the synth's drum voice (bass drum/tom as drum body and low thump, snare/cymbal/hi-hat as the bright top), rather than emulated.

Five built-in styles are included per engine: Synthwave, Chip Deluxe, Orchestral Lite, Dry, and Studio (a port of an offline remaster mix, with a fixed detuned-saw lead and a light bus compressor). Every instrument parameter can also be tuned without recompiling, via an `EnhancedAudioPresets.cfg` file placed in the Mesen home folder — the NES engine reads sections like `[Studio]`, the Game Boy engine `[Studio.Gb]`, and the SMS-family engine `[Studio.Sms]`, so each can be tuned independently from the same file. Edits to the file are picked up on console reset / ROM load (the file is never read from the audio path). A fully documented template with every field and the built-in defaults is included at [docs/EnhancedAudioPresets.example.cfg](docs/EnhancedAudioPresets.example.cfg) — the SMS and Game Boy tunings are inherited from the NES engine and still need ear-calibration, so that's the place to start.

This feature was originally proposed upstream as [PR #262](https://github.com/nesdev-org/MesenCE/pull/262). It was built with the help of AI tools, which the upstream project's contribution policy does not allow, so the PR was closed and this work now lives here instead, for personal use.

## Built to stay correct

*"AI-accelerated" only means something if there's a harness catching what it gets wrong.* Every push runs through CI-gated automated tests, not just a build check:

- **`core-unit-tests`** — a dependency-free C++ harness (`scripts/core_unit_tests.cpp`, `make core-unit-tests`) that exercises core logic directly: the Enhanced Audio channel-role classifier, MEP pack parsing, and other logic pulled out of the emulator core specifically so it *can* be tested without booting a ROM or a GUI.
- **`UI.Tests`** — a C# xUnit suite (`UI.Tests/`) covering the UI/host logic layer: cheat-code parsing, disabled-pack-list handling, and the MEP pack-list parser and zip validator that back the enhancement-pack UI.

Both run on every push and pull request via GitHub Actions ([`unit-tests.yml`](.github/workflows/unit-tests.yml)), independent of the native build — no SDL2, no full emulator core, results in seconds. It isn't exhaustive coverage of every console's core emulation; it's real, growing coverage of the logic this fork actually adds and changes, so refactors and new features get caught before they ship instead of trusted on faith.

## Enhancement Packs — one format, not five

Textures, music, and synth presets ship as a single hash-keyed pack (**MEP**), matched to your ROM automatically by its No-Intro hash — no manual setup, no per-game config. Drop a folder or `.zip` into `EnhancementPacks/`, and every layer (textures / audio / synth) can be toggled independently from the *HD Packs* menu.

And you don't have to wait for someone to build one: loading a game with no pack installed already starts building a starter pack for you next to the ROM — upscaled textures from what's actually on screen, with automatic music extraction landing the same way — so there's always something better than raw pixels and raw chip audio to fall back on, and an artist has a real starting point instead of a blank canvas.

Built on existing community formats wherever one already exists (No-Intro hashes, HDNes `hires.txt`, VGM/GD3, SMF/General MIDI, MSU-1/OGG) rather than inventing new ones — and where a gap remains, we publish small, open, CC0 specs so any pack author or emulator can adopt them too: [ESP v1](docs/specs/ESP-v1.md) (synth presets) · [MEP v1](docs/specs/MEP-v1.md) (the pack format) · [MEI v1](docs/specs/MEI-v1.md) (pack discovery).

Extraction stays local and the project only ever ships tools, mappings, and specs — never other people's game assets — so using it, or building packs with it, stays on solid legal ground.

## Built with AI, on purpose

This fork is developed with heavy use of AI tooling — implementation, code review, and the automated test suite described above are all AI-assisted. That's a deliberate trade, not a shortcut: it's what makes it realistic for a small, personal project to keep four emulation cores, an audio synthesis engine, and a pack-format ecosystem moving at the same time, with tests gating every change instead of manual review being the only net.

It's also why this lives as an independent fork rather than a series of upstream pull requests: MesenCE/Mesen2's contribution policy doesn't allow AI-assisted PRs (the [Enhanced Audio feature itself was closed upstream for exactly this reason](#enhanced-audio-nes-game-boy-sms-game-gear-sg-1000)). Rather than fight that policy, this fork develops in the open under its own roadmap, with an [ADR trail](.dev-squad/adr/) recording the reasoning behind each significant decision — so the "why," not just the "what," stays reviewable even without upstream code review.

Being a fork of free software cuts both ways, and AI is what makes the upside actually pay off: core accuracy fixes, timing corrections, and other improvements landed upstream in [MesenCE](https://github.com/nesdev-org/MesenCE) or [Mesen2](https://github.com/SourMesen/Mesen2) can be reviewed and ported into this fork quickly instead of piling up as a merge backlog — so diverging for the sake of enhancement features doesn't mean drifting away from upstream's own emulation-accuracy work.

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
