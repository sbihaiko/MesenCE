# Execution Plan — Phase 5: Automatic Pack Bootstrap (convention over configuration)

**Status:** in progress (2026-08-25) — F5.0 ✅ partial (ADR-0044 and ADR-0049 accepted; ADR-0047 accepted in F5.3; 0045/0046/0048 superseded), **F5.1 ✅** (sibling folder > `HdPacks/` > `EnhancementPacks/`; zip/folder named like the ROM without `pack.json`; human merge > `auto/` in the NES/GB/SMS/ESP loaders; `patches[]` + iNES hash normalization + `ApplyPatchOnHashMismatch` override in the UI; `scripts/mep_lint.py`; 28 headless checks — GB 1:1 across 5 scenarios, Zelda with 3 dumps, patch skip/apply; dotnet 0 warnings) · **F5.2 ✅** (`BootstrapEnhancementFolder` setting, default on: on load, when no texture pack applies at all, exports ROM tiles + records the tiles played with xBRZ 4x into `<Game>/auto/textures/` (+ `.bootstrap`); falls back to `EnhancementPacks/<Game>/` when the ROM folder is read-only; second load already uses the layer; *Open Game Folder* button; 18 headless checks — GB, SMB3 CHR ROM 8275 tiles, Zelda CHR RAM, opt-in, read-only folder) · **F5.3 ✅** (music recorder in the NES bootstrap: per-frame `NoteFrame` from the APU state → `TrackSegmenter` (60 frames of silence closes a track; ≥180 frames = `bgm`, otherwise `sfx`) → `auto/audio/fingerprints.json` + `midi/<id>.mid` (SMF/GM); `scripts/mep_render_audio.py` renders `bgm/<id>.ogg` (fluidsynth+SoundFont or an internal numpy synthesizer → ffmpeg libvorbis); on load, `NesAudioReplacer` loads the `auto/audio` → `audio` layers (human id wins), recognizes the track by its first onsets (±3 frames, confirms at 8), and plays the OGG through `HdAudioDevice` while muting pulse/triangle/noise; 90 frames of silence restore the APU; 12 headless checks with Zelda — records, renders, second load shows `fingerprint match 'track01' … APU muted`, human layer, warning when there's no OGG) · **F5.4 in progress** — reordered based on evidence from `mep_compare.py` (ADR-0050): **F5.4a ✅ static screens** (`auto/textures/backgrounds/screenNNN.png` of the whole screen without sprites + 3 `tileAtPosition` anchors + `<background>…,20`; not merged under the human layer; 21 headless checks on Zelda/Mega Man/Excitebike; `<background>`/`<condition>` serialization bugs fixed) · **F5.4a′ ✅ assets without playing**: static export now covers CHR RAM games via PRG scanning (alignment voted per bank + silhouette churn; 87–91% of Zelda's tiles, 80–83% Castlevania, 99% Mega Man) and the gray ramp is recolored with the real palette when drawing (previously an export-only pack rendered the game in gray); `*.orig.png` as an unfiltered reference; 24 headless checks (amendment to ADR-0043) · **F5.4f spike ✅ (ADR-0051, proposed)**: `scripts/spike_sound_driver` discovers the game's sound driver using the debugger (write breakpoints on the APU → tick; `JSR` scan by absolute address → "play N" entry point + id register) and enumerates the tracks by calling the entry point with each id over a title-screen save state — Mega Man: `S=$9003`, `A=id`, ids 0–50 → 18 bgm + 22 sfx + 11 very short ones, 40 distinct signatures, without playing; with `SPIKE_BOOTSTRAP=1` the F5.3 recorder wrote 50 tracks (18 bgm + 32 sfx) into `fingerprints.json` + 50 MIDI files in a 5-minute run · **F5.4b ✅ palette variant cap** (`HdPackBuilder::ProcessTile` already gave each distinct `PaletteColors` of a shape its own `HdPackTileInfo` — the old fallback to the wildcard entry `DefaultTile` (`GetKey(true)`, `PaletteColors=0xFFFFFFFF`) was dead code, since no real PPU palette produces that sentinel value; what was actually unbounded was per-shape growth: nearly/fully flat tiles render the same under any background palette, so a single near-blank shape reached 71 variants in a pre-cap 20-second recording on `roms/Zelda.nes`. This item adds `MaxPaletteVariantsPerTile` = 32 per shape (`HdPackBuilder.h`/`CaptureOrCapPaletteVariant`) — above the cap, capture only adds usage to the shape's last already-captured variant, without creating a new entry and without choosing by palette proximity; `scripts/validate_palette_variants.py` (20-second `hdpack` recording on Zelda): 174/182 tile shapes with more than 1 distinct palette captured (pre-existing capability, not regressed), a maximum of 32 palettes on a single shape (average ≈ 12.1 palettes/shape), no shape exceeds the cap and 1 shape hits it exactly) · F5.4c `mep_build.py`, F5.4d UI coverage, F5.4e sheets/objects pending · **F5.4g Block A ✅** (level-2 sound, ADR-0052: `ChannelRoleClassifier` decides per window which channel is lead/harmony/bass and which ones are playing SFX — fast hardware sweep, glide ≥ 7 st, non-periodic retriggers ≥ 3 st, pitch above A7 — with hysteresis and switching only at note boundaries; SFX rendered dry, outside the sends; `EnhancedSynthEngine` plays the music voices and percussion via **TinySoundFont** when a `.sf2` is present (`EnhancedAudio.SoundFontPath` or `<home>/EnhancedAudio.sf2`), falling back to the DSP; `EnhancedAudioAutoRoles`/`EnhancedAudioSfxSeparation`/SoundFont settings/UI; `scripts/roles_probe` validates headless: SMB 18/18 jumps as SFX, Zelda title screen 1 false positive of 0.08s in 30s, Mega Man/Castlevania coherent roles; GB/SMS go through the same routing) · Blocks B–D pending · F5.5 pending ·
**PRD:** [PRD-ecossistema-enhancement-comunitario.md](PRD-ecossistema-enhancement-comunitario.md) §Phase 5 (re-scoped) ·
**Spec:** [MEP-v1.md](../specs/MEP-v1.md) (gains `patches[]` and the sibling-folder convention; `pack.json` becomes optional) ·
**Order:** proposal to move F5 ahead of F4 (browser/MEI): without good, easy-to-produce packs, a browser just lists an empty catalog. F4 stays intact in the PRD and comes in afterward.
**Process:** ADRs first (F5.0), then blocks F5.1→F5.5, each with headless validation via `scripts/headless_record` as in phases 1–3.

## Principle: convention over configuration (ADR-0049)

> Running a game generates, next to the ROM and with the same name, a
> folder with automatically optimized textures and audio. That folder **is**
> the pack and is the artist's starting point.

Design consequences, all aimed at eliminating mapping:

- **No mandatory `pack.json`** — hash and system come from the ROM alongside
  it; `pack.json` only exists for publishing (`mep pack` generates it).
- **Two layers by location** — `auto/` belongs to the machine (freely
  regenerable); everything outside `auto/` is human and is never touched.
  Precedence per entry: human > `auto/`. No layer ids and no `provenance.json`.
- **Names are keys** — `audio/bgm/<track>.ogg` replaces the same-named track
  in `auto/`; `textures/sheets/<object>.png` replaces the cells of the
  same-named generated sheet. `hires.txt` is always **generated** (`mep build`).
- **Local folder wins over the zip** — order: sibling folder > `HdPacks/<Game>/`
  (legacy) > `EnhancementPacks/` (folders and zips). The artist works in the
  folder next to the ROM without uninstalling/disabling anything; the folder
  zipped as-is (`<Game>.zip`, without `pack.json`) installs in the emulator
  as a complete pack.
- **Automatic trigger** — setting "Bootstrap enhancement folder" (default on):
  on load, if the folder doesn't exist or the generator is newer, it records
  during play and materializes `auto/` on unload/power-off.

```
<dir>/Mega Man 3 (USA).nes
<dir>/Mega Man 3 (USA)/
  textures/  hires.txt (generated)  sheets/*.png (editable)
  audio/     bgm/*.ogg  sfx/*.ogg  midi/*.mid  stems/*_ch<n>.wav
  synth/     preset.cfg
  auto/      textures/  audio/  synth/       ← regenerated, never edit
  .bootstrap (generator version, sha1, timestamps)
```

## Origin: what two real packs taught us (2026-08-24/25)

We installed and ran **Contra80s** (HDNes, NES CHR RAM) and **Zelda Remastered v1.3**
(HDNes, PRG0 + IPS + 10 BGM/42 SFX OGG) in MesenCE.

| Observation | Pack | Response in this plan |
|---|---|---|
| CHR RAM game: static export (ADR-0043) covers nothing; recording only | Contra | Bootstrap combines **export + recording** while playing; coverage report |
| Nonexistent `Stage1.png` and `tileNearby` over `<background>` only show up in the load log | Contra | **Linter** (F5.1) running in `mep build` and in the UI's Install |
| 53 warnings ignored for years | Zelda | same |
| `tileNearby` with large offsets to disambiguate identical tiles in different contexts | Zelda | Candidate conditions **inferred from the recording** (F5.4), commented `# inferred` |
| A 1px offset beyond the screen crashed the emulator (off-by-one upstream, fixed) | Zelda | Linter validates coordinates; host keeps the checks |
| Audio depends on an **IPS** that alters the game code; tied to a single sha1 | Zelda | `patches[]` by hash + dump normalization (ADR-0044); **patch-free** trigger via APU fingerprint (ADR-0047) |
| Alternate folder with 8-bit SFX = "levels" done by hand | Zelda | Human layer vs. `auto/` by convention (ADR-0049) |
| No file states where an asset came from | both | Provenance **by folder**: `auto/` = machine |

## Success criterion (PRD §F5, rewritten)

> Playing for 5 minutes generates, next to the ROM, a folder with the game
> **enhanced** (image level 2, sound level 2/3) with no configuration at
> all; from it, an artist reaches a **publishable** pack in < 1h by editing
> only PNG/OGG.

Validation targets: **Mega Man 3** (NES CHR ROM), **Contra** (NES CHR RAM),
**Link's Awakening** (GB), **Sonic** (SMS). Each block closes with a
headless screenshot/log comparable to the baseline.

## The level ladder

Image: 0 original · 1 global filter (runtime xBRZ, no pack) · **2 auto**
(ROM tiles + captured ones → per-tile upscale, in `auto/textures`) · **3 enhanced**
(tiles grouped into objects, per-object upscale, sheets) · **4 inferred
conditions** · **5 art** (human edits sheets).

Sound (revised on 8/25, see F5.4g): 0 APU · **1** real-time Enhanced Audio
(F1: fixed roles pulse1=lead / pulse2=harmony / triangle=bass, DSP timbres)
· **2 automatic GM cover** (channel role per window, SFX separated from music,
arpeggio→chord, APU expression → GM instrument via SoundFont in real time;
optional human adjustment in `synth/preset.cfg`) · **3a identified tracks**
(machine: fingerprint + seed MIDI in `auto/audio`, recorded while playing
or by driving the game's driver — F5.3/F5.4f; doesn't change the sound by
itself) · **3b art** (musician replaces `audio/bgm/<track>.ogg`; the host
swaps it in at the right moment).

Level 2 is what every user hears on the first load of any ROM; 3a feeds 3b;
3b overlays 2 only for the tracks that exist. Level 3a lives in `auto/`; 3b
lives outside it. That's it.

## Current state (verified in the code on 2026-08-25)

| Item | Status |
|---|---|
| Static tile export | ✅ ADR-0043 |
| Tile recording + merge | ✅ F2 (GB/SMS) and upstream (NES) |
| Batch per-tile upscale | ❌; xBRZ/HQx exist **at runtime** (`Core/Shared/Video/`) — reusable offline by the core (no external dependency) |
| Export MIDI/VGM | ✅ F1, headless |
| Knowing **which music played when** | ❌ continuous MIDI; no segmentation and no trigger (ADR-0047) |
| Render MIDI → OGG | ❌ external (fluidsynth + free soundfont); without it, `auto/audio` only has MIDI |
| `<bgm>/<sfx>` NES | ✅ `HdAudioDevice` + `OggMixer`; requires a write to `$4100+` → today only via IPS |
| `<bgm>/<sfx>` GB/SMS | ❌ (ADR-0041) — out of scope until the draft freeze |
| Pack discovery | `HdPacks/<rom>/` and `EnhancementPacks/`; ❌ ROM sibling folder |
| Multiple MEP targets | ✅ `targets[]`; ❌ `patches[]`; ❌ dump normalization |
| Linter | ❌ log messages on load only |
| Continuous background recording while playing | ❌ the builder only records while its window is open |

## F5.0 — Phase ADRs (blocks the rest)

1. **ADR-0049 — Sibling folder as pack** (location, fixed layout, two layers
   per folder, load-time trigger, fallback to `EnhancementPacks/<Game>/` when
   the ROM folder isn't writable).
2. **ADR-0044 — Permissive targets**: dump normalization (trailing `00`
   beyond the iNES header size) + `patches[]` by sha1; patch skipped with a
   warning when it doesn't match; opt-in "ignore patch hash" toggle.
3. **ADR-0047 — Patch-free BGM/SFX trigger**: fingerprint of APU writes
   (same tap as the F1 exporter) → events for `OggMixer`; confirmation over
   K frames; coexists with the IPS mechanism.
4. Decide in F5.0: (a) whether upscaling runs **in the core** (reusing
   xBRZ, zero dependency) or in `scripts/`; recommendation: core for images,
   `scripts/` for audio rendering (PRD: heavy AI/tools never embedded).
   (b) background recording policy: limited buffer (e.g., 10 min of unique
   tiles + MIDI), CPU cost measured in the harness.
   **Decided in F5.2:** (a) upscale **in the core** — the HD Pack Builder
   already applies xBRZ/HQx/Scale2x per tile when saving, so the bootstrap
   is the existing builder pointed at `auto/textures` with xBRZ 4x; (b)
   recording uses the builder as-is (dedup by key, no extra buffer) and
   only runs when **no** texture pack applies — with the `auto/` layer
   present, the second load doesn't re-record (the builder would swap the
   PPU and hide the pack).

## F5.1 — Discovery via sibling folder + linter + permissive host ✅

**Deliverable:** a hand-created `<Game>/` folder (with just
`textures/hires.txt`) already loads; offline linter; `patches[]`.

- `MepPackManager`: scans the sibling folder `<ROM dir>/<name without extension>/`
  → synthetic pack (target = ROM sha1, system = from the ROM, sections =
  folders present, `auto/` as a second source). Order: **sibling >
  `HdPacks/` > `EnhancementPacks/`**. Zips in `EnhancementPacks/` without
  `pack.json` match by name (= ROM name), with the same layout as the folder.
- Validation: sibling folder + identical zip installed → log shows the
  folder winning; delete the folder → zip takes over, identical screenshot.
- Human > `auto/` merge per entry in the three loaders (NES hires.txt,
  GB/SMS `HdTilePack`, audio hires.txt, ESP: `auto/synth/preset.cfg` <
  `synth/preset.cfg` < user).
- `scripts/mep_lint.py <folder|zip>`: pack.json (if present), hires.txt
  (files exist, conditions allowed per type, 256×240 coordinates,
  `*Nearby` offsets within range), duplicate keys, PNG a multiple of the
  scale. Exit ≠ 0 on error. Oracle: Contra80s (4 errors) and Zelda (53
  warnings + the crash offset).
- ADR-0044 in the core (`ComputeNoIntroSha1`, `MepPack::Parse`,
  `NesConsole::LoadHdPack`).
- Headless validation: Zelda with the user's three dumps → textures in all
  three, patch only on the trimmed one; GB 1:1 with a pack in a sibling
  folder; `mep-off` unchanged.

## F5.2 — Image bootstrap (level 2) ✅

**Deliverable:** playing generates `auto/textures/` with upscaled tiles;
on/off setting.

- Background recording (no builder window): ROM export (ADR-0043) on load
  + capture of unique tiles while playing (limited buffer).
- On unload/power-off: tile-by-tile xBRZ 4x upscale (core) →
  `auto/textures/hires.txt` + PNGs; `.bootstrap` with version/sha1;
  `textures/sheets/` still **empty** (F5.4) — but should a human hires.txt
  be generated as an editable copy? **No**: the human hires.txt is only
  born from `mep build` starting from sheets. Before F5.4, the artist can
  edit the PNGs from `auto/` by copying them into `textures/` under the
  same name (name = key).
- Coverage report in the log and in the HD Pack Builder window (tiles seen
  vs. tiles with art; CHR RAM warning — lesson from Contra).
- Validation: MM3, Contra, LA, Sonic → second load loads `auto/`; headless
  screenshot ≈ runtime xBRZ.

## F5.3 — Sound bootstrap (level 3) + patch-free trigger

**Deliverable:** `auto/audio/` with per-track MIDI (+ OGG when fluidsynth
is present) and `fingerprints.json`; playback via fingerprint.

- Segmentation of the recorded MIDI/VGM into tracks (silence / pattern
  restart / tempo change) → `audio/midi/<track>.mid` + signature.
- `scripts/mep_render_audio.py` (fluidsynth + free soundfont → OGG q5)
  called by the emulator if available; otherwise a log message with
  instructions.
- Host: `FingerprintMatcher` (ADR-0047) feeds `OggMixer`;
  `audio/bgm/<track>.ogg` (human) wins over `auto/audio/bgm/<track>.ogg`.
- Headless validation: MM3 title screen → `[MEP] audio: fingerprint match
  'title'` in < 30 frames; APU mutes; zero false positives in 60s.

**How it turned out (✅):** the recorder lives in the core
(`NesAudioBootstrap`, fed after `_apu->EndFrame()`), not in the F1
exporter — no GUI and no dependency on the Enhanced Synth being on. Tracks
get ids `track01…`/`sfx01…` (the artist renames them in the human
`fingerprints.json`). OGG rendering stays outside the emulator
(`mep_render_audio.py`; without fluidsynth it uses an internal chip-synth
as a placeholder). MM3 and SMB3 don't play music in the first few seconds
without input, so validation uses Zelda (title screen with music from
frame ~60). Recognition latency = 8 onsets (~1s into the Zelda theme) —
the start of the track comes from the APU, the OGG kicks in from there
on; ADR-0047 documents the switch.

## F5.4 — Sheets, objects, and inferred conditions (levels 3–4)

**Order revised on 8/25 (ADR-0050)** — the comparison against
Castlevania/Contra80s/Zelda Remastered (`scripts/mep_compare.py`) showed
that the artist works in terms of screens and context, not tiles: (a) ✅
capture static screens as `<background>` with `tileAtPosition` anchors;
(b) automatic palette variants (7.6 palettes per bitmap in Zelda); (c)
`mep_build.py`; (d) "what you played" coverage in the UI; (e) only then
sheets/objects — they require more coverage than the 12–29% you get from
a few minutes of play.

- Spatial co-occurrence in the recorded frames → objects; sprites via OAM.
- Per-object upscale → `auto/textures`; `textures/sheets/<object>.png`
  generated (editable) + cell order in a comment in the generated
  hires.txt.
- `scripts/mep_build.py <folder>`: sheets → tiles → `textures/hires.txt`;
  new OGGs in `audio/`; runs the linter. `mep pack <folder>` → MEP zip with
  `pack.json`.
- Ambiguous tiles → candidate `tileNearby` marked `# inferred` for review.
- Validation: MM3 turns into coherent objects; Zelda Remastered as the
  conditions oracle (a metric, not a gate).

### F5.4f — Audio without playing (spike ✅ Mega Man, ADR-0051)

The F5.3 recorder only sees what the player triggers.
`scripts/spike_sound_driver` (`make spike-sound-driver`) shows it's
possible to **drive the game's own sound driver** with no per-game
knowledge: (A) write breakpoints on `$4000–$4017` + call stack → the tick
routine `P` and the driver's region; (B) `JSR`s from outside the driver's
bank into it, broken down by absolute address during a pulsed Start →
entry point `S` and the id register; (C) for each id, reload the
title-screen save state, break at `P`, set `PC=S`, `A=id`, return to a
`JMP` in RAM, and sample the APU for 4s. Mega Man: 18 bgm, 22 sfx, 11 very
short ones across 51 valid ids; the F5.3 recorder produced 50 tracks +
MIDI in the same run. Generalization (12 ROMs from the library, empirical
validation: ≥3 distinct ids and the same id reproducible across two save
states, via *new* onsets): Mega Man, Castlevania (`JSR`), Zelda
`$0600/$0602`, Punch-Out `$0722`, SMB3 `$04F5/$04F1` (mailbox via trace)
✅; Ninja Gaiden ⚠️; 1943/Contra/Excitebike/Gauntlet/SMB1/Bomberman ❌ (the
request doesn't happen in the title→Start window). Proposed decision
(ADR-0051): ship it as an opt-in tool (*Extract audio*), not automatic on
load — item 11 in F5.4g.

### F5.4g — Level-2 sound: automatic GM cover (ADR-0052; Block A ✅ 8/25)

Today `EnhancedSynth` (F1) re-synthesizes the APU with fixed roles and DSP
timbres: it works on any game, but Mario's jump plays with a lead timbre
and the bass turns into melody whenever the composer swaps channels. Level
2 is the ceiling of what's achievable **without knowing the music** — a
decent, automatic GM cover, with SFX left intact. All at runtime, with no
`auto/`, no human step.

| # | Item | Automatic | How |
|---|---|---|---|
| 1 | Channel role per window | ✅ done | `ChannelRoleClassifier` (Core/Shared/Audio): ~1s exponential moving average of register, onsets/s, and audible fraction; bass = lowest-register channel if ≤ C4 and ≥ 5 st below the next one (otherwise the default channel), lead = highest `register + 2·onsets/s` with a margin of 4 over the current one; switching only after 3 decisions (0.75s) and at a note boundary for the channels involved |
| 2 | SFX vs. music | ✅ done | cues: fast hardware sweep (≥ 12 st/s, ≥ 4 st), software glide ≥ 7 st at ≥ 12 st/s (the Zelda title screen glides 6 st), ≥ 5 retriggers in 140ms covering ≥ 3 st with no 2–4 note cycle (arpeggio/vibrato stay music), note > A7; holds up to 40ms of silence or 1.5s of continuous sound; the SFX channel goes to `Input::Sfx[]` = dry pulse with no echo/reverb; channel features freeze during the SFX. "Channel stolen and returned" was left for Block B |
| 3 | Arpeggio → chord | ✅ | periodic alternation of 2–4 notes at 20–60 Hz becomes a sustained chord |
| 4 | Expression | ✅ | decay, vibrato, and portamento extracted from the APU → choice (pluck × sustained × strings) and modulation of the voice; today `Input` only carries freq/vol/duty |
| 5 | Real timbres | ✅ done | `Utilities/Audio/tsf.h` (TinySoundFont, MIT) inside `EnhancedSynthEngine`: channels 0/1/2 = lead/harmony/bass (note-on on attack or a jump > 0.6 st, pitch wheel ±24 st follows the chip, channel volume follows the envelope), channel 9 = percussion (hi-hat 42 / kick 36 / tom 45 on noise attack); programs per preset (`GmLeadProgram`/`GmHarmProgram`/`GmBassProgram`/`GmDrums`, harmony with a fast attack since it carries arpeggios); `.sf2` from `EnhancedAudio.SoundFontPath` or `<home>/EnhancedAudio.sf2`, loaded in the constructor/reset (never during mixing); no file → the previous DSP. **Pending (user decision):** bundling a SoundFont in the repo/installer — GeneralUser GS (31MB, permissive own license, provenance of some samples uncertain) or MuseScore General (206MB, MIT) |
| 6 | Human override | partial | the GM programs are already preset fields, so `synth/preset.cfg` (ESP) and `EnhancedAudioPresets.cfg` override them; fixed per-channel role is left for Block B |
| 7 | Validation | ✅ done | `scripts/roles_probe` (`make roles-probe`): runs the ROM headless with a save state and scripted input, feeds the same classifier with the sampled APU, and prints a timeline (roles, SFX segments with the cue that triggered them) + statistics; `--wav`/`--sf2` record the mix. Results from 8/25: SMB1 18/18 jumps (sweep+glide+retrig), Castlevania whip 3/3, Zelda title screen 1 false positive of 0.08s/30s (was 10 before calibrating sweep/glide), Mega Man 2 role swaps at the title→stage-select transition; WAV with no clipping, GM ~ same RMS as the DSP. Still missing an ear in the GUI |

Amendments to 3a/3b (F5.3/F5.4f) still needed for the OGG replacement to
be usable: **8** loop point in the fingerprint (`LoopPosition` is 0
today); **9** SFX audible during the OGG (today pulse/triangle/noise are
muted entirely — depends on item 2); **10** direct music→music transition
and fade (today only 90 frames of silence restore the APU); **11**
extraction without playing as an opt-in tool (*Open Game Folder → Extract
audio*), a longer window/stimuli for Contra/SMB1, and separate music and
SFX triggers; **12** naming/cleaning up enumerated ids; **13**
`mep_build.py`/`pack` with `audio/`, audio lint, and a "seed-MIDI to OGG"
tutorial.

Order: **Block A** 2→1→5→7 ✅ (changes what every user hears) · **Block B**
3, 4, 6 (+ "channel stolen and returned", fixed per-channel role in the
ESP) · **Block C** 8, 9, 10 · **Block D** 11, 12, 13. Each block roughly
the size of F5.3.

GUI validation (8/25): "remastered" packs that replace the music with OGG
(Zelda HD: `ZeldaHD.ips` + `<bgm>`) hide level 2 — the Enhanced Audio
toggle appears to do nothing. Response: the first pack OGG shows a warning
on the OSD; *Audio (OGG)* under *Enhancement Packs* now gates **all** pack
OGG (HDNes `<bgm>/<sfx>` and fingerprint-based replacement), live; a new
**ROM patch** layer (`EnablePatches`) allows turning off the IPS while
keeping the textures, since the patch is what mutes the original music.
Everything goes to `<home>/mesen.log` (with `.1`).

Lessons from Block A: a hardware sweep is **not** a reliable SFX signal
(Zelda's driver uses it for 2 st musical slides); distance traveled
separates better than speed (musical slides stay ≤ 6 st, effects go past
8); a slow-attack pad on the harmony swallows arpeggios (RMS dropped 5x in
Zelda until the program was swapped); the makefile doesn't track headers —
growing `AudioConfig`/`EnhancedSynth` without deleting the dependent `.o`
files produced a `new` with a stale `sizeof` and a SIGSEGV during mixing.

## F5.5 — Wrap-up

- UI: bootstrap setting; HD Pack Builder with "Open game folder", coverage,
  before/after preview; Enhancement Packs lists the sibling folder with
  origin "sibling".
- Specs: MEP-v1 §sibling folder and `patches[]` (minor 1.1; `pack.json`
  optional only for the folder form); golden updated; `validate-specs.py`.
- README/PRD §F5; F1–F3 regressions; dotnet build 0 warnings.

## Risks

| Risk | Mitigation |
|---|---|
| Cluttering the ROM library with folders | setting (default on, one click to turn off); fallback to `EnhancementPacks/` when not writable |
| CPU cost of background recording | limited buffer, measured in the harness, turns off if frame time rises |
| Fingerprint false positives | K frames, per-track tolerance, IPS fallback, toggle |
| "Generic"-looking automatic upscale | it's a bootstrap, not the product; sheets reduce the cost of doing it manually |
| External audio dependencies | optional; without them the bootstrap still delivers MIDI |
| Evolving the format breaking v1 | everything is additive; a folder without `auto/` = a regular pack |

## Out of scope for this phase

- Browser/MEI index (F4) — later.
- OGG GB/SMS (draft freeze).
- ML-model-based upscale — comes in as an alternative to xBRZ in `scripts/`, later.
- Automatic IPS relocation across revisions.
