# Contributing to this fork

This is a personal fork of [MesenCE](https://github.com/nesdev-org/MesenCE). It exists because the work here — the Enhanced Audio engine and the broader [Community Enhancement Ecosystem](docs/enhancement-ecosystem.md) — is built with the help of AI tools, which the upstream project's [contribution policy](https://github.com/nesdev-org/MesenCE/blob/master/CONTRIBUTING.md) does not allow. There is no upstream PR flow for this work; it lives here.

**Product branch is `main`.** `master` is a frozen full-console snapshot. Do not use GitHub **Sync fork** and do not `git merge upstream/master` into `main` — that reintroduces consoles this fork dropped (SNES including SGB, PC Engine, WonderSwan, ColecoVision). Remaining cores: NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA. Bugfixes from upstream are cherry-picked file-by-file. Code taken *from* upstream still follows upstream's style (clang-format / dotnet format) so those cherry-picks stay readable.

## Licensing

- **Code** is licensed under the **GPL v3**, like the rest of Mesen (see [LICENSE](LICENSE)). Contributions must be GPL-compatible. This fork makes no MIT relicensing claim over its own additions.
- **Open specs** under `docs/specs/` (ESP, MEP, MEI, the hires.txt GB/SMS extension) are **CC0 / public domain**, so any emulator or pack author can implement them without touching GPL code. By contributing to a spec you agree your contribution to it is CC0.

## Tools, never content

The repository ships **tools and clean data only**: source code, synth presets, ROM-hash mappings, index manifests, documentation. Never commit derivative content — extracted tiles, ripped samples, transcribed MIDIs, covers, or third-party pack art (see the [ecosystem principles](docs/enhancement-ecosystem.md#principles)).

**One deliberate exception:** short before/after demonstration excerpts and gameplay screenshots in `docs/media/`, the same de facto practice every emulator's documentation relies on — kept brief, credited where a community author is involved, never full tracks or complete asset sets.

## AI-assisted code

AI-assisted contributions are **welcome** in this fork. You remain responsible for the result:

- Review and understand what you submit — you are the author of record.
- Test it (build on at least one platform; for Enhanced Audio changes, verify by ear against the reference games listed in the presets template).
- Keep the emulation cores accurate: enhancements are a layer *on top of* accurate emulation and must never affect determinism, save states, rewind, or movies.

## Style

The fork keeps upstream's style so cherry-picks stay cheap. It is enforced with clang-format (C++) and dotnet format (C#):

- clang-format: `find ./ -iname '*.h' -o -iname '*.cpp' | xargs clang-format -i`
- dotnet format: `dotnet format`

Naming conventions:

- ExampleFunction
- exampleVariable
- _exampleMemberVariable

When in doubt, follow the formatting you see elsewhere in the project.

## Quality bar

- **Performance:** avoid new work in hot paths (press F9 to run at an unlocked framerate and F10 to view FPS); the enhanced synth must never regress the audio thread.
- **Warnings:** MSVC builds treat warnings as errors; Linux clang builds use `-Werror`. Resolve them.
- **Context:** commit messages and PRs should explain the *why* and name the games/ROMs used to verify the change.
