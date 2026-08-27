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
content in `pack.json` (the `sections` field, see MEP-v1.md §3). The final
verdict is one of the three below.

### Aceito (MEP completo)

The pack includes, in addition to textures, at least one `synth` or `audio`
section:

- **`synth`** (MEP-v1.md §5.3) — a file in **ESP v1** format, applied above
  the built-in defaults and below the user's local ESP.
- **`audio`** (MEP-v1.md §5.2) — an audio replacement directory in a format
  already supported by the target system (OGG for HD pack, or MSU-1 on SNES).

### Aceito parcial (HD Mesen)

The pack only declares the **`textures`** section (MEP-v1.md §5.1): a
directory pointing to an HD Pack in HDNes `hires.txt` format. This is a
valid and complete submission within the scope of textures, but it does not
cover audio/synth, so it receives the `pack:partial-hd` label instead of
`pack:mep-full`.

### Inválido

The submission is rejected when:

- the link is not on the allow-list of accepted hosts, or the download
  exceeds the size limit;
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
