# Authoring HD/MEP Packs for community submission

This guide is for anyone filling out the "Community HD/MEP Pack Submission"
form (`.github/ISSUE_TEMPLATE/community-pack.yml`). It summarizes what makes
a pack get accepted, partially accepted, or rejected during the automatic
triage on the "MesenCE Community Packs" board.

The full normative specification is [`docs/specs/MEP-v1.md`](specs/MEP-v1.md)
(RFC 2119, CC0-1.0 license). This document does not replace the spec — it
just translates the sections relevant to someone preparing a submission.

## What triage checks

When the submission issue is opened, a workflow downloads the pack from the
provided link, runs `scripts/mep_lint.py` on it, and classifies the declared
content in `pack.json` (the `sections` field, see MEP-v1.md §3) or, for a
plain HD Mesen pack, its `hires.txt`. The verdict is **binary** — `accepted`
or `invalid` (ADR-0138 Clarification §2) — and is reflected on the
"MesenCE Community Packs" board through the Status field, whose option names
are literals: "Novo envio" → "Em validação" → "Aceito parcial (HD Mesen)" /
"Inválido". ("Aceito (MEP completo)" remains a defined Status option but is
not an automated target; there is no separate full-MEP verdict.)

### Accepted — Status "Aceito parcial (HD Mesen)"

The pack lints clean and at least one declared section actually resolves
inside the archive. Every `accepted` submission receives the `pack:valid`
label; **what** the pack contains is conveyed by additive content-index
labels, never by the verdict itself:

- `assets:textures` — a **`textures`** section (MEP-v1.md §5.1): a directory
  pointing to an HD Pack in HDNes `hires.txt` format (or a plain HD Mesen
  pack, `hires.txt` at the root).
- `assets:audio` — an **`audio`** section (MEP-v1.md §5.2): OGG replacement
  tracks in the format already supported by the target system. A **`synth`**
  section (MEP-v1.md §5.3, an **ESP v1** file applied above the built-in
  defaults and below the user's local ESP) is validated by the lint but has
  no label of its own.
- `patch:ips` / `patch:bps` — the pack ships a ROM patch (`patches[]`).
- `console:nes` / `console:gb` / `console:gbc` / `console:sms` — the console
  declared in the form.
- `assets:external` — a split-distribution pack assembled through an
  `external_assets` recipe (see "Split-distribution packs" below).
- `pack:split` — a sibling issue that the triage opened for one game of a
  multi-game archive (`scripts/validate_pack_local.sh`).
- `pack:needs-review` — the identity check found the same `pack_id` claimed
  from a different origin (ADR-0140/0141); a human decides.

### Invalid — Status "Inválido" (`pack:invalid`)

The submission is rejected when:

- the link is not on the allow-list of accepted hosts (GitHub
  releases/archives, gist/raw, Google Drive, MediaFire `/file/` links), or
  the download exceeds the size limit;
- `scripts/mep_lint.py` fails (invalid `pack.json` structure, sections, or
  paths);
- the pack violates the spec's security section (MEP-v1.md §6): zip entries
  that escape the pack directory (zip-slip), or any indication that the pack
  attempts to package executable bytes instead of declarative data;
- there is an obvious content/licensing problem (e.g. assets extracted from
  the ROM without distribution rights, or credits clearly missing).

## Release zips with a wrapper/promo folder

Some releases package the pack inside a freely-named subfolder (e.g.
`Contra80s-v1.1/...`), sometimes alongside material that is not part of the
pack (screenshots, a promotional README). This does not match any
first-class convention: there is no `pack.json` at the zip root, and the zip
is not named exactly like the ROM (MEP-v1.md §2.1, rules 5-6).

For this case there is a **last-resort compatibility path**
(MEP-v1.md §2.1, rule 9), but automatic triage and the MesenCE host locate
the candidate subfolder using different criteria — the engine-vs-validators
asymmetry documented in MEP-v1.md §2.1:

- **MesenCE host (`PrepareZip`, which decides whether the pack loads in the
  game)** looks, inside the zip, for the subfolder whose **name matches the
  ROM's name** (case-insensitive, no extension) — the same criterion as
  rule 5. For your pack to work in the host through this fallback, **name
  the internal subfolder exactly like the ROM**.
- **Automatic triage (`mep_lint.py`) and the UI validator
  (`MepZipValidator.cs`)** instead use a **structural** (name-agnostic)
  criterion: they accept the subfolder whose contents match the fixed
  layout (`textures/hires.txt`, `audio/hires.txt`,
  `audio/fingerprints.json` and/or `synth/preset.cfg`), without looking at
  the name. A pack can pass structural triage and still fail to load in the
  host if the subfolder is not named like the ROM.

In both cases, the fallback only runs after the normal conventions fail,
and if the zip has **more than one** candidate subfolder, the submission is
rejected for ambiguity — so avoid packaging more than one content folder
per zip.

This fallback is a last-resort feature, not the recommended way to publish:
whenever possible, put `pack.json` at the zip root, or name the release
file/folder itself exactly like the ROM (no extension), so the submission
is accepted by the first convention without depending on the fallback or
the criteria difference described above.

## Split-distribution packs (MEP Recipe)

Some releases cannot ship a single self-contained zip: the textures/patch
live in your release, but the referenced audio (or another dependency) is
distributed separately — for example because it is too large for the CI
download cap, or because you do not hold redistribution rights for the
audio files themselves. For this case triage can assemble a **MEP
Recipe** — a declarative instruction set (never executable code) that
tells the host how to combine your primary pack with the externally-hosted
files at install time — from two optional sections, `external_assets` and
`external_assets_license`.

The submission form no longer asks for them (it is down to three required
fields), so add them yourself: after opening the issue, edit its body and
append the sections in the same shape the form used to produce, i.e. a
`### External assets (optional)` heading followed by your dependency
lines, and a `### External assets license (optional)` heading followed by
the license. The parser reads them exactly as before. The full normative
vocabulary is [`docs/specs/MEP-recipe-v1.md`](specs/MEP-recipe-v1.md)
(ADR-0138); this section only explains what to put in them.

### `external_assets`

A multi-line section. One dependency per non-empty line; blank
lines and lines whose first non-space character is `#` are ignored. Each
line is whitespace-separated:

```
<url> [<sha256>] [<size>]
```

- `url` — where the file can be downloaded (a direct link, not an HTML
  landing page).
- `sha256` — the SHA-256 of the file's exact bytes, as **64 lowercase hex
  characters** (compute it with `sha256sum <file>`).
- `size` — the file's size in bytes, as a decimal integer. Optional, but
  recommended.

**A line missing `sha256` disables recipe assembly for the entire
submission** (ADR-0138 §12): triage cannot trust an unverified download, so
the recipe step is skipped and the submission falls back to the normal
pre-recipe verdict path, with a comment explaining which line is missing
its hash and how to add it before commenting `/revalidate`.

### `external_assets_license`

An optional single-line section for the declared license of the files listed
in `external_assets` (e.g. an SPDX identifier or a short free-text
description). This is shown to installers before the dependency is used —
it does not replace your own distribution-rights responsibility for the
primary pack (see "Before submitting" below).

### The `assets:external` label

When a recipe is successfully assembled from your `external_assets` lines,
the issue receives the `assets:external` label in addition to whatever the
primary pack contains (`assets:textures`, `assets:audio`). This is an
additive content-index label, like the others — it never becomes a third
verdict state; the verdict stays binary with Status "Aceito parcial (HD
Mesen)" / "Inválido" (ADR-0138 Clarification §2).

That said, a viable recipe **does** change the outcome for a
split-distribution pack: a submission whose referenced files are hosted
externally and whose recipe dry-runs clean is judged `accepted` (`pack:valid`
+ `assets:external`), where the exact same pack with no `external_assets`
declared — or no viable recipe — would stay `invalid` under MEP-v1 §5
(ADR-0138 Decision §2). What §2's downgrade-only rule actually constrains is
the deterministic recipe gate itself: when a recipe is present, the gate may
only **downgrade** an already-`accepted` classify verdict to `invalid` (a
schema failure or an unclean dry-run) — it never **upgrades** an `invalid`
classify verdict. So declaring `external_assets` is worth doing whenever your
pack references files you cannot bundle: it is the mechanism that can turn
an otherwise-`invalid` split pack into an `accepted` one, not a no-op.

## Border (bezel) layer

Since MEP v1.5 (MEP-v1.md §5.4, ADR-0149) a pack can ship a decorative
frame — bezel, cabinet art, Super Game Boy-style border — drawn around the
game. It is optional, it is the only thing in its section, and a pack may
consist of a border alone.

**Files.** Put them in a `border/` folder at the pack root and declare it:

```
<pack>/
  pack.json                 "sections": { ..., "border": { "path": "border/" } }
  border/border.png         required — the frame, 32-bit RGBA; its pixel size is the canvas
  border/border.json        optional — where the game goes
```

In the folder-form/sibling-folder layout (no `pack.json`) the same
`border/border.png` is picked up automatically; a bootstrap or tool may
write a machine-generated one under `auto/border/border.png`, and the
human `border/` always wins over `auto/` (the same human > auto rule as
textures and audio). MesenCE also accepts a bare `border.png` at the pack
root, but the lint only recognizes the `border/` folder — use the folder.

**`border.json`** (the file is optional; once present, `width`, `height`
and a full `viewport` are required — see the spec table for exact rules):

```json
{
  "version": 1,
  "width": 1920, "height": 1080,
  "viewport": { "x": 240, "y": 0, "width": 1440, "height": 1080 },
  "scale_mode": "fit",
  "underlay": false
}
```

- `width`/`height` document the PNG size (the host always trusts the PNG;
  keep them equal to it).
- `viewport` is the rectangle, in canvas pixels, where the game frame is
  drawn (`x`, `y`, `width`, `height`, all integers >= 0; keep it inside the
  canvas or the lint warns and the host clips it). The game is scaled to
  fill it exactly, so give it the game's aspect ratio (4:3 for NES/SMS,
  10:9 for Game Boy). Leave the PNG fully transparent there, or partially
  transparent for a soft bezel edge.
- Without `border.json` (or without a usable `viewport`) the host assumes a
  16:9 bezel around a 4:3 game: a viewport as tall as the canvas, 4/3 as
  wide, centred horizontally.
- `underlay: true` draws the PNG *behind* the game instead of blending it
  on top (the game covers the whole viewport opaquely).
- `scale_mode` is `fit` (default) or `stretch`. The current MesenCE build
  parses it but still hands the canvas to the normal video scaler (your
  aspect-ratio/integer-scale settings apply), so do not rely on `stretch`
  yet.

A `border.png` that fails to decode is skipped silently — the game keeps
running without a frame — so always run `python3 scripts/mep_lint.py
<pack>` before submitting: it reports a missing `border.png` as an error
and prints the decoded frame size (`border frame PNG 1920x1080`); it also
checks every `border.json` field.

**Toggling it in the emulator.** The border is gated by its own switch,
"Border" in the Player shell's Enhancements quick-toggle panel (next to
Textures/Audio) and the "Enable pack border" checkbox in *Enhancement
Packs* (Advanced mode). It defaults to on; turning it off costs nothing and
restores the plain game frame.

## Seeding audio for your pack (record → MIDI → OGG)

A pack's `audio/` layer is the pair `audio/fingerprints.json` (which track
plays for which id, MEP-v1 §2.1) plus the OGG files under `audio/bgm/` and
`audio/sfx/`. The workflow below turns a game's own sound driver into that
layer without recording audio manually:

1. **Record the seeds.** Either play the game in Mesen with the F5.3 audio
   recorder active (the bootstrap writes `auto/audio/fingerprints.json` +
   `midi/` next to the ROM), or, for a headless pass over a specific title,
   run the extract-audio tool (ADR-0135) on its own copy of the ROM:

   ```bash
   make spike-sound-driver
   scripts/spike_sound_driver "<rom.nes>" "<workdir>" "<pack-folder>" [maxIds] [secondsPerId] [startAt] [wallClockBudget]
   ```

   The tool drives the game's sound driver through the debugger (no
   gameplay), validates a trigger, enumerates ids, and writes
   `<pack-folder>/auto/audio/fingerprints.json` + `midi/` plus
   `enumeration.log` beside them. When no trigger validates it writes only
   the log ("no validated trigger") — the pack folder is left untouched.
   Expect it to take minutes (it runs the game at real time); `wallClockBudget`
   caps the worst case and `Ctrl-C` aborts at a frame boundary, keeping what
   was already written.

2. **Render the MIDI to OGG.**

   ```bash
   python3 scripts/mep_render_audio.py <pack-folder> [--sf2 path/to/generaluser-gs.sf2]
   ```

   With `fluidsynth` + a General MIDI SoundFont this gives a GM render of
   each track under `auto/audio/bgm/`; without a SoundFont the internal chip
   synthesizer writes a placeholder timbre close to the original NES chip.
   The renderer never overwrites a human-layer OGG.

3. **Listen, prune, promote.** `enumeration.log` lists every id with its
   kind (bgm/sfx/short/title), length, hash and first notes;
   `scripts/audio_cleanup_suggest.py <pack-folder>` summarises which ids
   look like garbage (short/title/repeat/silent) from the log. Delete the
   garbage ids from `audio/fingerprints.json`, rename the keepers
   (`scripts/mep_build.py rename-audio-id <folder> <old-id> <new-id>`),
   set a MIDI loop marker where a track should loop (MEP-v1 §5.2 `loop`),
   and move the good OGGs from `auto/audio/bgm/` to `audio/bgm/`.

4. **Build and lint.** `scripts/mep_build.py <pack-folder>` regenerates
   `audio/hires.txt` from the OGGs, applies the split-pack conventions, and
   runs the MEP linter — the audio lint (fingerprints schema, resolved
   `<bgm>`/`<sfx>` targets, `loop` sanity) is part of that gate, so an
   invalid audio layer is a build failure, exactly like a broken texture
   layer.

This is the seed-MIDI→OGG path: the seed MIDIs come from the game itself,
are rendered once, and a human curates the result — no manual recording or
transcription required.

## Before submitting

- **Distribution rights.** The pack MUST NOT contain ROM bytes or assets
  extracted from it without distribution rights — this is the pack
  author's responsibility (MEP-v1.md §1).
- **Valid `pack.json`.** Check it against the example in MEP-v1.md §3: the
  `mep`, `name`, `version`, `targets` (with the ROM's No-Intro `sha1`), and
  `sections` fields are required.
- **Run the lint locally before submitting**, if possible:
  `python3 scripts/mep_lint.py <pack-folder-or-zip>`.
- **Direct download link**, hosted on one of the accepted hosts: a GitHub
  release, `raw.githubusercontent.com`, or a gist. Links to HTML pages (not
  to the file itself) are not accepted automatically.

## After submitting

An automatic comment on the issue records the verdict, the spec section it
is based on, and moves the item on the board. If you update the pack at the
same link after a verdict, comment `/revalidate` on the issue to trigger a
new check — the content hash is always recomputed, so an actual change to
the pack is detected even without this command (periodic drift check).
