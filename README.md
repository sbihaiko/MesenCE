# Mesen Community Edition

Mesen is a multi-system emulator for Windows, Linux, and macOS. It supports NES, SNES, Game Boy (GB/SGB/GBC), Game Boy Advance, PC Engine, SMS/Game Gear, and WonderSwan (WS/WSC).

This is a community-managed fork, created to maintain and expand this emulator into the future.

## About This Fork

This is [sbihaiko](https://github.com/sbihaiko)'s personal fork of MesenCE, built on top of the upstream project above.

### Enhanced Audio (NES)

This fork adds an experimental **Enhanced Audio** mode for the NES core: an alternative synthesizer that reinterprets the live APU channel state (frequency, volume, duty) with modern instrument timbres in real time, on any ROM, with zero per-game assets. The APU stays the source of truth — the synth only reads its state and mixes on top of (or replaces) the original chip output. Enable it from the NES audio settings.

Five built-in styles are included: Synthwave, Chip Deluxe, Orchestral Lite, Dry, and Studio (a port of an offline remaster mix, with a fixed detuned-saw lead and a light bus compressor). Every instrument parameter can also be tuned without recompiling, via an `EnhancedAudioPresets.cfg` file placed in the Mesen home folder.

This feature was originally proposed upstream as [PR #262](https://github.com/nesdev-org/MesenCE/pull/262). It was built with the help of AI tools, which the upstream project's contribution policy does not allow, so the PR was closed and this work now lives here instead, for personal use.

## Releases

The latest stable version is available from the [releases page on GitHub](https://github.com/nesdev-org/MesenCE/releases).

## Development Builds

[![Mesen](https://github.com/nesdev-org/MesenCE/actions/workflows/build.yml/badge.svg)](https://github.com/nesdev-org/MesenCE/actions/workflows/build.yml?query=branch%3Amaster)

* [Windows](https://nightly.link/nesdev-org/MesenCE/workflows/build/master/Mesen%20%28Windows%20-%20net10.0%20-%20AoT%29.zip)
  * Windows 7 or higher is required. Windows 7 users must use SP1 and have all updates installed.
* [Linux x64](https://nightly.link/nesdev-org/MesenCE/workflows/build/master/Mesen%20%28Linux%20-%20ubuntu-22.04%20-%20clang_aot%29.zip)  (requires **SDL2**)  
* [Linux ARM64](https://nightly.link/nesdev-org/MesenCE/workflows/build/master/Mesen%20%28Linux%20-%20ubuntu-22.04-arm%20-%20clang_aot%29.zip)  (requires **SDL2**)  
* [macOS - Intel](https://nightly.link/nesdev-org/MesenCE/workflows/build/master/Mesen%20%28macOS%20-%20macos-15-intel%20-%20clang_aot%29.zip)  (requires **SDL2**)  
* [macOS - Apple Silicon](https://nightly.link/nesdev-org/MesenCE/workflows/build/master/Mesen%20%28macOS%20-%20macos-15%20-%20clang_aot%29.zip)  (requires **SDL2**)  

#### <ins>Notes</ins> ####

* Other builds are also available in the [Actions](https://github.com/nesdev-org/MesenCE/actions/workflows/build.yml?query=branch%3Amaster) tab.
* **macOS**: Builds are self-signed and will require approval via Gatekeeper before they are able to be run.  
* **SteamOS**: See [SteamOS.md](SteamOS.md)  

## Compiling

See [COMPILING.md](COMPILING.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

## License

Mesen is available under the GPL V3 license.  Full text here: <http://www.gnu.org/licenses/gpl-3.0.en.html>

Copyright (C) 2014-2026 Sour, 2026 contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
