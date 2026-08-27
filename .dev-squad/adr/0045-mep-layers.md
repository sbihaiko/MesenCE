# ADR-0045: Layers inside a MEP pack (auto / enhanced / art)

- Status: superseded by ADR-0049 (folder convention replaces the manifest: layers = top-level vs `auto/`, provenance = location, sheets/midi/stems = fixed paths)
- Date: 2026-08-25
- Phase 5, F5.2–F5.5. Extends MEP v1 (minor bump 1.1).

## Context
Zelda Remastered ships an alternate folder with 8-bit SFX: "levels" done by
hand, switched by renaming folders. The F5 pipeline produces three qualities
of the same entry (auto-upscaled, object-grouped, artist-made) and users must
be able to pick, per pack, how far up the ladder they go. Between packs we
already have ADR-0040 precedence; inside a pack there is nothing.

## Decision
Optional `layers` per section:

```json
"textures": { "path": "textures/", "layers": [
  { "id": "art",      "kind": "art",      "path": "textures/art/",      "default": true },
  { "id": "enhanced", "kind": "enhanced", "path": "textures/enhanced/", "default": true },
  { "id": "auto",     "kind": "auto",     "path": "textures/auto/",     "default": true }
]}
```

- Resolution is per **entry** (tile / background / bgm / sfx), precedence
  `art > enhanced > auto` among enabled layers; each layer is a complete
  hires.txt (or audio hires.txt) loaded and merged by the host.
- No `layers` ⇒ one implicit `art` layer at `path` (today's behaviour).
- UI: one checkbox per layer in the Enhancement Packs window; persisted like
  per-pack toggles (container + layer id).

## Consequences
- Regenerating the `auto` layer never touches `art` (see ADR-0046).
- Loader cost: up to 3 hires.txt merges per section — acceptable (load time).
- HDNes packs stay untouched; they are single-layer.
