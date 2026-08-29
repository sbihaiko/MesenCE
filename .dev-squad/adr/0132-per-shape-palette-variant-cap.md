# ADR-0132: Per-shape palette-variant cap in the HD Pack Builder

- Status: accepted (decided; the cap has shipped in the code since F5.4b and is
  listed as a slice in the PRD — "F5.4b follow-ups | (a) saturation log when a
  shape hits `MaxPaletteVariantsPerTile`; (b) seed `_paletteVariantsByShape`
  from `_hdData` or document per-session scope | ADR-0132". Follow-ups (a) and
  (b) were implemented on 2026-08-29; this ADR was written retroactively the
  same day, since no ADR file had ever been created for the original cap.)
- Date: 2026-08-29
- Related: ADR-0043 (HD pack static export and UI expectations), ADR-0034
  (small focused methods)

## Context

`HdPackBuilder::ProcessTile` (F5.4b, `Core/NES/HdPacks/HdPackBuilder.cpp`)
captures one `HdPackTileInfo` per distinct `PaletteColors` value it sees for a
given tile shape. A shape is `tile.GetKey(true)` — tile content with
PaletteColors wildcarded, so every palette variant of the same pixels
collapses into one shape. Per-shape growth is what was genuinely unbounded: a
mostly/fully flat tile (e.g. all-zero TileData) renders identically under any
background palette, so unrelated screen state alone can rack up dozens of
"distinct" PaletteColors sightings for one shape with no artistic value.

Measured on a 20s `roms/Zelda.nes` hdpack recording pre-cap: 182 shapes,
median 14 variants/shape, p95 15, p99 27, and a single all-zero blank-tile
shape alone reaching 71 — the long tail the cap targets.

## Decision

1. **Cap.** A shape may hold at most `MaxPaletteVariantsPerTile = 32` real
   palette variants. 32 sits above the measured p99 so real per-shape
   diversity survives intact and only the degenerate/near-blank outliers get
   bounded. Beyond the cap, further sightings just bump usage on the shape's
   last captured variant instead of growing the pack further.

2. **Follow-up (a) — saturation log.** When the cap is reached, log a
   one-time `[HDPack]` message per shape (guarded by a `_variantCapLogged`
   set of shape hashes) so the artist sees the shape saturate instead of
   failing silently, without spamming the log every frame the flat tile is on
   screen.

3. **Follow-up (b) — seed from disk.** Seed `_paletteVariantsByShape` from
   the on-disk pack at construction (`HdPackBuilder` ctor load block),
   excluding `DefaultTile` neutral-ramp placeholders (they await art; the
   loader ignores their PaletteColors, so they are not real variants). The cap
   is therefore a per-shape **total** across re-record sessions, not a
   per-session ceiling — a re-record no longer stacks up to 32 more variants
   on top of what is already on disk.

## Consequences

- Pack files stay bounded in size for flat-tile-heavy games (blank tiles,
   solid-color walls) while keeping genuine per-shape palette diversity.
- Artists editing a pack see a shape's true variant count in the log; a
   saturation message is the signal to draw art for that shape, not to add
   more palette shots.
- Loading an existing pack costs one extra pass over `_hdData.Tiles` in the
   builder constructor (only when a pack already exists on disk).
- The "most recently captured variant" fallback after a seed starts from the
   last on-disk entry in `_hdData.Tiles` order until the session captures its
   first new variant for that shape.
