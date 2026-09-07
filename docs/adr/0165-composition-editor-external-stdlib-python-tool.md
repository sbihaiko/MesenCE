# ADR-0165: The composition editor is an external stdlib Python tool in `scripts/`, a tkinter layered canvas over a host-free engine

- Status: accepted (2026-09-07, by the user; PRD Part A slice F9.18)
- Date: 2026-09-07
- Related: ADR-0164 §3–§5 (data, output contract, layer model), ADR-0153 §2/§4 (sidecar schema, precedence, contexts, `_SHEET_RANK`), ADR-0154 (external-script posture, no downloads), ADR-0147 (`mep/` as the artist's pack folder), ADR-0156 (screen-owned nodes), ADR-0160 (`chr/` pixel source), PRD Part A §4 Phase 9 (F9.18)

## Context

ADR-0164 shipped the data the composition editor needs — `textures/sheets/adjacency.json`, written by the sheet pipeline — and defined the editor's contract: §3 the `usrNNN` output sheet (an ordinary `object`/`sprite` sidecar with `composed`/`seed`/`locked` and, for a sprite layer, `band`), §4 where a composed sheet lives (`auto/` until painted, `mep/` once it is the artist's work), §5 the layered-canvas model (one layer per sheet kind; the sprite Y-band query as the genuinely new idea; seed → rank → lock → recompute inside a layer; export). Its Consequences fixed two acceptance tests and said plainly: "it does not ship the editor."

What ADR-0164 deliberately left open is the tool's own form — it is "the external tool this ADR exists for", with no stack, location or seam decided. F9.18 is that separate slice. Three constraints shape the decision this ADR makes:

- **The editor is interactive by nature** — it paints. But this project's pattern for artist-facing work is external scripts under `scripts/`, Python stdlib only, nothing downloaded, the emulator core untouched (ADR-0154). The emulator must not grow an editor, and the two acceptance tests are **ranking assertions** that must run headless, with no window.
- **The editor's output must be ordinary pipeline input.** In-place edits to `hud`/`font`/`background`/`object` sheets and a kept sprite band exported as `usrNNN` both have to round-trip through `mep_build.py` unchanged (ADR-0153 §4, ADR-0164 §3). The editor adds no new format; it only produces sidecars and PNGs the existing pipeline already slices, with `_SHEET_RANK` ranking by `kind` and `usrNNN` sorting after `objNNN`/`sprNNN` in `sorted()` load order.
- **Some pixels cannot come from a sheet.** A background node no sheet shows is a screen-owned node (ADR-0156): its pixels are in the `backgrounds/screenNNN.orig.png` the routing named, or renderable from `textures/chr/` by its `tiles[]` keys (ADR-0160). ADR-0164 §3 forbids silently substituting a blank; the editor needs that rule as its own pixel-source policy.

Decisions this ADR therefore makes, and no more: (1) form/stack/location of the tool; (2) the seam between the interactive canvas and the headless parts the two acceptance tests exercise; (3) the scope of F9.18's first delivery inside §5's model; (4) pixel sourcing and write-back/promotion. Everything ADR-0164 §3–§5 already fixed (the sidecar fields, the band query math, the precedence) is cited, not re-decided.

Non-goals, in ADR-0153/0164's own terms: no emulator or runtime concept, no new `hires.txt` construct, no change to `mep_build.py`'s consumers, no separate *rendered* planes (that is a `hires.txt` format change, ADR-0004 at v1-draft, with its own ADR in the mould of ADR-0149), and no AI repaint of composed output (ADR-0154 is unchanged and applies as-is).

## Decision

**1. Form and stack — an external Python tool in `scripts/`, stdlib only.**

The composition editor is a set of Python modules under `scripts/` (`compose_` prefix) plus one entry point, `scripts/compose_editor.py <pack folder>`. It opens a pack folder on disk, reads `textures/sheets/*.json` with their `.png`/`.orig.png` twins plus `adjacency.json`, and writes only sheet files — the inputs `mep_build.py` already reads. The interactive canvas is **tkinter**, which is system-provided (verified available on this machine: Python 3.12, Tk 8.6) and therefore satisfies ADR-0154's no-download posture. No third-party dependency, no new `Core/`/`UI/` file, no `.vcxproj`/`.csproj` entry.

**2. Engine seam — the tested path never imports tkinter.**

The logic is split so nothing interactive lives where the tests reach:

- `scripts/compose_engine.py` (pure, host-free): opens a pack folder and builds the **scene** — one layer per sheet kind from the sidecars (HUD/font, background from `map-NNN`/`metatiles`/a `screenNNN` capture, objects from `objNNN`, sprites from `sprites.json` + `adjacency.json`), on a canvas sized to a screen or a stitched map region (ADR-0164 §5); materialises the sprite layer as one sub-layer per Y band (`sprites.nodes[].floors[]` bottom edge quantised to 8 px, joined with `sprites.pairs[].coFrames`, ranked by `coFrames × band overlap`); runs seed → rank → lock → recompute inside a layer, with near-field `offsets[]` placing a candidate's figure (its `sprNNN` group) relative to the locked ones when one exists; exports a kept band as a `usrNNN` sheet carrying ADR-0164 §3's fields (`composed: true`, `seed`/`locked`, `band { bottom, tolerance: 8 }`); and writes in-place cell edits back into the `hud`/`font`/`background`/`object` sheets.
- `scripts/compose_editor.py` (tkinter view) is a thin controller over the engine. Engine code never imports tkinter, so `test_compose_engine.py` and CI run headless.

The two ADR-0164 acceptance tests are the slice's green gate, run as suites in the repo's Python harness against the engine — seed a Ninja Gaiden metatile that `obj000.json` groups, lock its strongest neighbour, and the recomputed ranking must place the rest of `obj000`'s cells first; and the Y band containing Ryu's bottom edge must rank the recording's ground enemies above any projectile. Both use synthetic `adjacency.json`/sidecar fixtures plus a real recorded pack when one is present; neither opens a window. GUI behaviour itself is judged by the human panel, not asserted.

**3. F9.18's first delivery is §5's whole model as an interactive canvas.**

This slice does not stage a headless motor first: it ships the layered canvas — HUD and font layers, background layer, object layers, and the sprite layer as one sub-layer per Y band — with seed-lock-recompute visualised inside a layer and the two export paths live (in-place sheets for HUD/background/objects; `usrNNN` per kept sprite band). "Usable cold" is the bar: open a pack recorded since F9.17, seed a cell from a layer, lock against it, and export without the artist opening `hires.txt` or a sidecar.

**4. Pixel source and write-back mirror ADR-0164 §3 exactly.**

The 1x pixels of a node come from whichever sheet shows it — the cell whose `metatile`/`aliases[].metatile` equals the node id, nearest-neighbour from that sheet's `*.orig.png`. A background node no sheet shows is taken from the `backgrounds/screenNNN.orig.png` the routing named, or rendered from `textures/chr/` by its `tiles[]`; never a silent blank. Painted crops are written back through the same slice/fan-out path `mep_build.py` uses, so precedence is unchanged (painted beats untouched, ADR-0153 §4). Placement follows ADR-0164 §4: work under `auto/textures/sheets/` is derived data; the moment the artist paints a sheet it is written to `mep/textures/sheets/` (ADR-0147), and the tool states this when asked to save to `auto/`. A pack without `adjacency.json` is reported as "no adjacency.json — re-run the bootstrap", never silently recomputed.

## Consequences

- Ships F9.18. The ADR-0164 acceptance tests are the gate; the human Phase 9 panel (cold-read, find-and-edit, seam) judges the composed output itself.
- One more artist tool and its test files under `scripts/`; no `Core/`/`UI/` change, no `Core.vcxproj` entry (ADR-0007). tkinter is assumed on the artist's machine (system Python; some distros need `python3-tk`); the engine and all tests never import it, so headless/CI are unaffected.
- The tool only means something on packs recorded since F9.17 (they carry `adjacency.json`); older packs get the re-bootstrap message. An edit written into an `auto/` sheet is lost on the next bootstrap unless it has been promoted to `mep/` — the promotion rule of ADR-0164 §4, surfaced in the save dialog rather than papered over.
- The sprite layer is the risky part and the reason the band criterion exists: its queries are over `floors[]`/`coFrames` accumulated with no distance cap, so the acceptance test on the Ryu band is what proves the far-field statistics are enough — no fallback to the thin `evidence[]` of the group sheets.

## Revision (2026-09-07, same day, after implementation)

Two clauses read more literally than the pipeline supports; both are recorded
here rather than diverged from silently, with the evidence that forced them.

- **"Cells edited in place" (§Decision 3) is external painting, not a tool
  write-back.** The compose tool's write path is always a new `usrNNN` sheet
  (kind `object`/`sprite`) whose PNG and `*.orig.png` twin start identical;
  the artist then paints `usrNNN.png` in an image editor and `mep_build.py`
  fans the painted cells out, as for any sheet. The tool never pastes pixels
  back into the builder's own `hud`/`font`/`metatiles`/`object` sheets,
  because doing so would *duplicate* an already-present cell: `mep_build.py`
  keys precedence on a PNG differing from its `*.orig.png` twin, so a copy
  pasted into the source sheet (and mirrored into the twin to keep the twin
  pixel-exact) either changes nothing or — mirrored — marks the copied cell
  untouched and ties against the very sheet it came from. "Edit in place" is
  therefore satisfied as ADR-0153 §4 always meant it: the artist repaints
  the sheet's PNG and the unchanged pipeline picks the painted cell up.
- **A screen-owned background node cannot be resolved to pixels from disk
  alone.** §Decision 4 and ADR-0164 §3 say the tool takes a node no sheet
  shows "from the `backgrounds/screenNNN.orig.png` the routing named" — but
  the ADR-0164 §1 sidecar records no routed screen (and no position) per
  node, and nothing else in the pack names one either. The engine therefore
  raises a `ComposeError` ("it is a screen-owned cell (ADR-0156) — compose
  it from the map/background layer, not as a bare cell") instead of pasting
  a blank. Closing the gap is a sidecar-format decision (persist the routed
  screen + offset per node in `adjacency.json`) and is out of scope here;
  it is the precondition for composing a bare screen-owned cell from the
  object layer.
