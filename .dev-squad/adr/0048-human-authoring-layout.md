# ADR-0048: Human-facing authoring layout (sheets, MIDI, stems) + `mep build`

- Status: superseded by ADR-0049 (folder convention replaces the manifest: layers = top-level vs `auto/`, provenance = location, sheets/midi/stems = fixed paths)
- Date: 2026-08-25
- Phase 5, F5.4/F5.5.

## Context
hires.txt is a machine format: one line per tile key, palettes in hex,
conditions by pixel offset. Both studied packs show authors fighting it
(missing files, wrong condition targets, out-of-range offsets). Artists work in
sprite sheets; musicians work in a DAW. The automatic layers (ADR-0045) are
meant to be raw material for them, so the material must be in their formats.

## Decision
The builder emits, next to the generated hires.txt:

- `sheets/<object>.png` — tiles grouped into objects (sprites via OAM
  size/flip; backgrounds via spatial co-occurrence in recorded frames) laid out
  as a sheet, plus `sheets/manifest.json` mapping sheet cells → hires.txt keys.
- `midi/<track>.mid`, `stems/<track>_ch<n>.wav` (per-channel render),
  `preset.cfg` (ESP) — one set per detected track (ADR-0047 segmentation).
- `scripts/mep_build.py <pack>`: recompiles sheets → tile PNGs and picks up any
  `<track>.ogg` dropped next to its MIDI, updating provenance (ADR-0046) to
  `artist:*` for changed cells/files, then runs the linter (F5.1).

Artists edit PNG/OGG only; hires.txt stays generated.

## Consequences
- Object grouping is heuristic; wrong groups only affect ergonomics, never
  correctness (cells still map 1:1 to keys).
- Two representations of the same data — `mep build` is the single source of
  truth for the compiled pack; sheets are inputs.
