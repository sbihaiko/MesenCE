# Open specs for the Enhancement Ecosystem (MesenCE)

Specs planned in the PRD
([`docs/roadmap/PRD-mesence-enhancement-ecosystem.md`](../roadmap/PRD-mesence-enhancement-ecosystem.md),
§2). All licensed **CC0-1.0** — any emulator or tool can implement them
without depending on MesenCE. Normative language per RFC 2119, semver
versioning, canonical golden files in [`golden/`](golden/), and automated
validation via `python3 scripts/validate-specs.py` (repo root).

| Spec | File | Status | What it defines |
|---|---|---|---|
| **ESP v1** | [`ESP-v1.md`](ESP-v1.md) | stable | grammar and fields of the Enhanced Audio preset (`EnhancedAudioPresets.cfg`) |
| **MEP v1.3** | [`MEP-v1.md`](MEP-v1.md) | stable | pack envelope (`pack.json` + No-Intro hash + textures/audio/synth sections); 1.1: `patches[]`, folder-form/sibling-folder without `pack.json`, `auto/` layer; 1.3: §2.1 rule 9 bare-basename discovery, §6 recipes-as-data |
| **MEI v1** | [`MEI-v1.md`](MEI-v1.md) | stable | federated pack-discovery manifest + trust model |
| **MEP Recipe v1** | [`MEP-recipe-v1.md`](MEP-recipe-v1.md) | stable | declarative re-packaging of split-distribution packs (`copy`/`glob`/`rename`/`rewrite-paths`) |
| **hires.txt GB/SMS** | [`hires-gbsms-v1-draft.md`](hires-gbsms-v1-draft.md) | **draft** | backward-compatible extension of the HDNes format for GB/SMS (pending community review — ADR-0004) |

**Reference implementation limitations (MesenCE, MEP v1 host — F3):** the
`audio` section is applied only to `nes` (OGG via `hires.txt`); GB/SMS await
the freeze of the hires-gbsms extension, and SNES/MSU-1 is out of scope for
the PRD's phases (ADR-0041). `.zip` packs are extracted to
`EnhancementPacks/.cache/` on first read; precedence among packs is the
lexicographic (case-insensitive) order of the container name, first wins
(ADR-0040) — a loose HD Pack in `HdPacks/<rom>/` beats the `textures` section
(§5.1), except for the ROM's sibling folder (`<dir>/<Game>/`, §2.1 —
F5.1/ADR-0049), which beats everything. `patches[]` and the hash normalized
to the iNES header size (ADR-0044) are implemented; the "apply patch with
divergent hash" override remains in *Enhancement Packs*. Offline linter:
`python3 scripts/mep_lint.py <folder|zip>`. Recipe interpreter (F6.1):
`python3 scripts/mep_recipe.py validate|dry-run|apply`. Bootstrap (F5.2, host behavior,
not part of the spec): with the option enabled and no applicable texture
pack, playing writes the tiles to `<Game>/auto/textures/` (xBRZ 4×) next to
the ROM and, on NES, the music to `<Game>/auto/audio/` (`fingerprints.json` +
`midi/`; F5.3/ADR-0047 — `scripts/mep_render_audio.py` generates the
`bgm/<id>.ogg` files, played by note recognition, without patching). Static
screens become `auto/textures/backgrounds/screenNNN.png` + `<background>`
with `tileAtPosition` anchors (F5.4a/ADR-0050); under a human layer, only the
`auto/` tiles are merged. When the ROM is opened, the static export covers
CHR ROM (all tiles) and CHR RAM (heuristic scan of PRG, amended ADR-0043);
`defaultTile` entries in a gray ramp are recolored with the real palette when
drawn.

Changes via issue/PR in this repository; a breaking change = a major version
bump of the affected spec.

Related tools in `scripts/`: `headless_record.cpp` (captures MIDI/VGM
without a GUI, `make capture-tool`), `make_gb_test_rom.py` (deterministic
homebrew ROM used by the hash goldens), `gen_mep_test_pack.py` (test MEP
packs — dir/zip/negatives — for a ROM), `mep_lint.py` (offline validation of
packs/hires.txt), `mep_recipe.py` (MEP Recipe v1 interpreter), and
`validate-specs.py`.
