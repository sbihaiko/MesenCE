# ADR-0166: The adjacency sidecar records, per screen-resident background node, the `screenNNN` that owns it and its on-screen offset

- Status: accepted (2026-09-07, by the user; closes the ADR-0165 Revision pixel-source gap, part of PRD slice F9.18)
- Date: 2026-09-07
- Related: ADR-0164 §1 (the background node schema), ADR-0165 §Decision 4 and its Revision (the pixel-source gap), ADR-0156 (screen-owned cells), ADR-0153 §4 (sheet precedence), ADR-0139 (content_id)
- Supersedes / amends: amends ADR-0164 §1 (adds an optional per-node field); closes the second open item of ADR-0165's 2026-09-07 Revision

## Context

ADR-0165's engine cannot source the pixels of a **screen-owned** background
node from disk. A scene cell whose every sighting a captured screen accounts
for (ADR-0156, F9.9) leaves `metatiles.png`, but stays in the vocabulary —
and ADR-0164 §3 tells the composition tool to take such a node "from the
`backgrounds/screenNNN.orig.png` the routing named". The problem is that
*the routing names no screen in the pack*: `adjacency.json` (ADR-0164 §1)
persists, per background node, only `cell/count/context/degrees/tiles`. The
tool therefore raises a `ComposeError` ("it is a screen-owned cell — compose
it from the map/background layer") instead of pasting a blank, which is the
honest behaviour but leaves a whole class of cells un-composable as bare
cells. ADR-0165's Revision records this as the sidecar-format gap that must
be closed before a screen-owned cell can be composed from the object layer.

The data the gap needs is produced at save time and then thrown away. Three
facts already hold in `HdPackBuilder` while the sheets are written:

- `MarkScreenResidentCells` decides residency, but the *owning screen* is a
  per-sighting fact: every resident cell is shown, at a fixed grid position,
  on at least one captured grid frame (`CollectCapturedSightings` records
  `Sighting {Cell, Row, Col, FineX}` per captured frame).
- `CaptureScreen` writes `backgrounds/screenNNN.png` and its `*.orig.png`
  twin (at the pack's scale, whole-frame), and keeps a `PendingScreen` per
  capture carrying `BaseName` (`screenNNN`), the `BitmapIndex`, and the
  `GridFrameIndex` of the grid frame it froze.
- `FinalizeScreenAnchors` correlates the two — anchors are chosen from the
  resident cells a specific captured screen shows — so the
  captured-frame → `screenNNN` correspondence exists at the moment
  `WriteAdjacencyFile` runs.

Non-goals: no per-screen sidecar (a second lookup path for one crop), no
CHR-render fallback (the bank → fragment mapping the engine would need is
not on disk either), no change to `hires.txt` or to where a screen capture
lives, and no new sheet kind. The fix is one optional field on the nodes
that need it, so older packs keep loading and simply lack the field.

## Decision

Extend `adjacency.json`'s `background.nodes[]` with an optional `screens`
array, emitted **only** on the nodes the captured-screen surface owns
(`ScreenResident`), i.e. exactly the nodes no ADR-0164 §3 source sheet
(`metatiles`/`hud`/`font`/`misc`) shows:

```json
{ "cell": 301, "count": 240, "context": "scene",
  "outE": 0, "outS": 0, "inE": 3, "inS": 2,
  "screens": [ { "screen": "screen003", "x": 14, "y": 11 } ],
  "tiles": [ { "tile": "<32 hex>", "palette": "0F162A30" } ] }
```

- `screen` is the file stem under `textures/backgrounds/` (the same stem the
  `PendingScreen.BaseName` and the `hires.txt` `<background>` condition
  use), so a consumer resolves the crop to exactly the file that shows the
  cell.
- `x`/`y` are the node's on-screen grid position in the 8 px tile
  coordinates the builder already places cells with (the same `Row`/`Col`
  `CollectCapturedSightings` records): the node's art origin is `(x*8, y*8)`
  in 1x NES screen pixels, and a `unit`-pixel crop there equals the node's
  tiles.
- A resident cell may sit on more than one captured screen (a town reused
  across two screens). `screens` lists every one that shows it — sorted by
  screen ordinal, deduplicated by `(screen, x, y)` — so the field is
  complete rather than a guess; a consumer uses the first entry, since
  duplicate placements of one vocabulary entry render the same pixels.
- `adjacency.json` stays **version 1**: the field is additive and optional,
  so the version number does not churn and a reader that ignores the field
  (including `mep_build.py`, which skips the file by kind) is unaffected. A
  pack recorded before this change simply has no `screens` and keeps today's
  behaviour and message.

**Producer.** `HdPackBuilder::WriteAdjacencyFile` (which already receives
the vocabulary and writes the bytes) walks the retained captured grid frames
and, for each `ScreenResident` entry, records the pending screens whose
`GridFrameIndex` maps to a frame that shows it, plus the frame's placement
`Row`/`Col`. Deterministic (screen ordinal order) so two saves of one
recording stay byte-identical and `content_id` (ADR-0139) does not churn
beyond the single re-bootstrap a new field always causes.

**Consumer.** The compose engine's background `node_art` fallback order stays
"sheet that shows it first"; a screen-owned node with `screens[0]` now crops
`unit` px from `backgrounds/<screen>.orig.png` at `(x*8, y*8)`, scaled by
that capture's resolution (the screen PNG and its twin are written at the
pack's scale, so the offset multiplies by the scale and the crop divides back
down to 1x by nearest neighbour). It must still never silently substitute a
blank: a node with neither a sheet nor `screens` keeps raising the compose
error naming the map/background layer.

**Validation.** The acceptance check for the slice is an invariant over a
freshly produced pack: every background node that no ADR-0164 §3 source
sheet shows has a non-empty `screens`, and cropping its first entry equals
the node's own `tiles[]` art. The exact pixel arithmetic for a
fine-scrolled resident cell (`FineX != 0`, the one corner case the 8 px
quantum does not pin) is calibrated during implementation against a real
still-game recording and recorded in the PRD row, as the F9.x threshold
calibrations were.

## Consequences

- `adjacency.json` grows a handful of bytes per resident node (a node list
  that is small by construction — the routing floors of ADR-0156 cap the
  routed share of the scene vocabulary). No new file, no new sheet kind, no
  `hires.txt` change.
- A re-bootstrapped pack gains the field and its `content_id` changes once,
  exactly as any re-bootstrap changes it (ADR-0164 Consequences). Existing
  packs are untouched until re-recorded, which is the ADR-0153/0160/0164
  position on migrations.
- The F9.18 compose engine gains a real crop path for screen-owned cells and
  a headless suite case for it; composing a bare scene cell the screen owns
  stops being an error and becomes an action the editor can offer.
- The field is only as good as the producer's placement bookkeeping: if the
  captured-frame → `screenNNN` correspondence drifts, the validation crop
  fails loudly rather than pasting wrong art — the invariant is what keeps
  the crop honest.
