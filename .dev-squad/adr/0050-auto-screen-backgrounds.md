# ADR-0050: Bootstrap captures static screens as `<background>` layers before inferring objects

- Status: accepted
- Date: 2026-08-25
- Fase 5, F5.4. Reorders the F5.4 plan (objects/sheets → backgrounds first).

## Context
Comparing the auto layer with three community packs (`scripts/mep_compare.py`,
25/08/2026) showed where the distance really is: xBRZ tiles are no closer to
the artist's result than raw pixels (MAE 56 vs 56.5 on Castlevania), and the
most elaborate pack (Zelda Remastered) barely works in tiles at all — 19 905
`<background>` lines conditioned by `tileAtPosition`, 93 % of the tiles in
common left transparent. Artists paint *screens*; the machine offered tiles.

## Decision
While the bootstrap records, a static screen (same background tile at every
pixel for 15 consecutive frames, ≥ 50 % of the frame drawn) is saved once as
`auto/textures/backgrounds/screenNNN.png` — the whole frame rebuilt from the
background tiles (no sprites) and upscaled in one pass with the pack filter —
plus up to three `tileAtPosition` anchors (rarest non-flat tiles on screen, ≥ 64
px apart) and a `[A&B&C]<background>…,1,0,0,20` line. Priority 20 (behind
foreground sprites) so the screen replaces the tiles and sprites still draw
on top. Per-session cap 300 screens; screens already in the pack keep their
numbers on re-record.

Under a human `textures/` layer the auto screens are **not** merged (only the
tiles are): a whole-screen PNG would hide the artist's tiles. The artist
promotes a screen by copying its lines (and PNG) into `textures/hires.txt`.

## Consequences
- The auto layer now yields exactly the artefact the best packs are built
  from; the first "paint over a screenshot" workflow needs no tooling.
- Animated screens (Zelda title waterfall, scrolling) never stabilise and are
  skipped by design — tiles still cover them.
- Two latent core bugs fixed on the way: `HdBackgroundInfo::ToString` dropped
  priority/scroll (a reload fell back to priority 10) and tile conditions
  serialised `tileData` and palette without the separating comma.
- Headless: `scripts/headless_record` now seeds the default 2C02 palette
  (the core reads `NesConfig.UserPalette` as-is; without the UI it was black).
