# ADR-0046: Per-entry provenance

- Status: superseded by ADR-0049 (folder convention replaces the manifest: layers = top-level vs `auto/`, provenance = location, sheets/midi/stems = fixed paths)
- Date: 2026-08-25
- Fase 5, F5.2+. Generalises the re-record merge rule of F2/ADR-0043.

## Context
Neither studied pack records where an asset came from. Once a pipeline can
regenerate assets (better upscaler, new soundfont), it must not overwrite what
a human made. The F2 builder already has a narrow version of this rule
("re-record merges on top of an export and keeps defaultTile entries").

## Decision
`provenance.json` next to each section's hires.txt:

```json
{ "tool": "mesence-hdpack-builder", "version": "…",
  "entries": { "<entry key>": { "source": "rom" | "capture" | "upscale:xbrz4" | "render:GeneralUserGS" | "artist:<name>", "date": "2026-08-25" } } }
```

- Entry key = the hires.txt key (tile key / background file / bgm album,track).
- Rule: automatic tools may overwrite an entry only when its source is not
  `artist:*`. Files edited by hand with no record are treated as `artist`
  when their hash differs from the recorded one (hash stored alongside).
- The host ignores provenance (authoring-only); the linter (F5.1) reports
  entries without it as `info`.

## Consequences
- Safe "regenerate auto layer" button.
- Credits/licensing per asset become derivable (PRD §3 legal architecture).
