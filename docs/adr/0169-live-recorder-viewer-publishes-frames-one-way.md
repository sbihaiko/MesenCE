# ADR-0169: The recorder publishes its frames one way, and the live viewer never blocks the run

- Status: accepted — implemented (uncommitted): the `live=<ms>` tap and the
  sprite-layer record in `scripts/headless_record.cpp`, the viewer
  `scripts/record_viewer.py`. The commit awaits human review.
- Date: 2026-09-08
- Updated: 2026-09-08 — the sprite-layer read channel switched from the
  debugger-based `GetMemoryState` to direct console exports under
  `Emulator::Lock()` (Context bullet 3, Decision 2, Consequences bullet 1); the
  record shape and the measured hold cost now match the implementation.
- Related: ADR-0050 (bootstrap screen backgrounds), ADR-0157 (headless input in
  emulated frames), ADR-0164 (adjacency sidecar), ADR-0165 (the composition
  editor is an external stdlib Python tool), ADR-0167 (HUD-only capture seam),
  ADR-0168 (proposed: the sprite composition unit)

## Context

A recording is a black box. `scripts/headless_record` prints a frame counter
and, at the end, writes a pack; everything an artist can look at — the
`backgrounds/screenNNN.png` screens of ADR-0050, the sheets, the
`adjacency.json` of ADR-0164 — exists only after the run is over. Whether the
run reached gameplay at all is not knowable until minutes later, when the pack
is composed and the art is drawn.

That is not a theoretical cost. In the 30-game sweep of the local library, five
games never left a menu, and each was discovered only after a full 400-emulated-
second run plus a composition pass. Gauntlet produced 202 distinct sprite nodes,
a rich vocabulary, entirely from its title screen. The composition editor
(ADR-0165) then asks an artist to compose from a vocabulary nobody has ever
watched being built.

Three facts make a live view cheap:

- The recording loop is already awake. `waitForPause("recording")` polls the
  frame counter every 2 ms for the stall watchdog, so a tap needs no thread.
- In-memory frame capture already exists — `HeadlessCaptureFrame` /
  `HeadlessReadCapturedPixels` (F9.15, `InteropDLL/EmuApiWrapperHeadless.cpp`),
  today called once at the end of a run.
- `NesConfig.DisableBackground` and `NesConfig.DisableSprites`
  (`Core/Shared/SettingTypes.h`) can separate the two planes by rendering, and
  the sprite layer can be read off the console directly. Reading it through
  `GetMemoryState` (`InteropDLL/DebugApiWrapper.cpp`) was tried and rejected:
  it goes through `WithDebugger`, and a headless run under a live debugger
  never parks on its target frame (`HeadlessInputEngine::ApplyFrame` refuses to
  pause when `IsDebugging()`), so the run would spin at full speed forever. The
  realized channel is a direct export, `HeadlessCaptureNesSpriteLayer`
  (`InteropDLL/EmuApiWrapperHeadless.cpp`), which holds the emulation thread at
  an end-of-frame boundary with `Emulator::Lock()/Unlock()` and reads OAM,
  palette RAM, the mapper-resolved CHR and the $2000 sprite-control bits — no
  debugger is attached, so the run still parks on its declared frame.

Non-goals. This is not a debugger and not a second emulator front end: the
viewer is read-only, the run stays scripted (ADR-0157), there is no rewind, no
input, no seeking, and nothing here runs in CI.

## Decision

### 1. The recording never depends on the viewer

`headless_record` gains `live=<ms>`, off by default. Every `<ms>` of wall clock,
inside the existing poll loop, it captures the current frame and publishes it by
**atomic file swap**: write `frame.ppm.tmp` into `<output-prefix>-live/`, then
`rename()` over `frame.ppm`. Alongside it, `status.json` — frame number, target
frames, elapsed wall clock, and a `done` flag — written the same way, plus a
final `done: true` status when the run parks on its target frame so the viewer
can show "finished" rather than stale data.

A FIFO or a socket is rejected, and the reason is not taste. Both make the
recorder's progress depend on a reader: a FIFO with no consumer blocks the
writer, and a socket with a slow consumer fills its buffer and then blocks.
Either one would stall the emulator, and the stall watchdog would kill the run —
so watching a recording could change or destroy it. A file swap is
lossy-latest, which is the correct semantics for a live view: a viewer that
falls behind must skip frames, never queue them. It also survives a viewer
restart, admits several viewers at once, and can be inspected with any image
tool.

If the live directory cannot be written, the run logs one line and continues.
A viewer that crashes is invisible to the recorder.

### 2. The sprite layer is read, not rendered

The composed frame is published as pixels. The sprite layer is published as
**data**: alongside each frame, the run writes the sprite layer as the console
sees it — OAM, palette RAM and the $2000 control bits read under an
`Emulator::Lock()` hold (Context bullet 3) — and the viewer draws the sprites
itself from those bytes plus the CHR of that moment.

The rejected alternative was to alternate `NesConfig.DisableSprites` and
`NesConfig.DisableBackground` between captures — cheaper, and no debugger. It
is rejected because the pack builder is watching the same frames: a frame
rendered with its background disabled would teach the metatile vocabulary a
blank screen. That approach would have to be mutually exclusive with
`bootstrap` and `hdpack`, making the layer view unavailable in exactly the run
someone wants to watch. Reading OAM perturbs nothing, so watching a pack being
built and watching its layers stay the same activity.

Reading the table also produces, per frame, the set of OAM entries on screen at
that instant — which is the grouping ADR-0168 argues the sprite composition unit
should be. This ADR does not decide ADR-0168; it stops the live viewer from
foreclosing it.

The published sprite record is, per capture: the frame number, and for each of
the 64 OAM entries its Y, tile index, attributes and X, plus the 32 bytes of
NES palette RAM (background and sprite sub-palettes as the PPU stores them,
first-slot mirror semantics included) and the $2000 control bits the
reconstruction needs (sprite pattern table, 8x16, sprite enable, left-column
mask). The CHR needed to resolve the referenced tiles is published alongside
each capture, and the run's 64-color RGB table once at startup. Sprite pixels
the viewer draws are therefore reconstructed, not captured — they can disagree
with the composed frame at the edges the PPU clips (the 8-sprite-per-scanline
limit, the left-column mask). The viewer labels the layer as reconstructed
rather than pretending otherwise.

### 3. The viewer

`scripts/record_viewer.py`, stdlib plus tkinter, following ADR-0165: an
external Python tool in `scripts/`, never linked into the emulator. It polls the
live directory, draws what it finds, and writes nothing. Given no run in
progress it says so rather than failing.

## Consequences

- No new Core source file, so `Core.vcxproj` and its filters are untouched and
  ADR-0007 is not triggered. The debugger-based read path is unusable rather
  than merely expensive: `GetMemoryState`/`GetPpuState` attach the debugger,
  and a headless run under a live debugger never parks on its target frame
  (`HeadlessInputEngine::ApplyFrame` logs "not pausing" and returns when
  `IsDebugging()`), so the run would never end. The realized channel attaches
  no debugger: `HeadlessCaptureNesSpriteLayer` reads under `Emulator::Lock()`,
  which parks the emulation thread at an end-of-frame boundary (it spins in
  `WaitForLock` with `_threadPaused` set) without touching the run's own
  pause/stop machinery, so the recording still stops on its declared frame.
  The cost of that hold is what this draft originally asked to measure;
  measured on a 5-second NES smoke, a 200 ms live tap added ~0.1 s of wall
  clock over the plain run (1.0 s vs 0.9 s) — noise against the 2-minute
  budget.
- `headless_record` grows a flag and a publish step in the poll loop. The
  publish must stay cheap: at 250 ms a 256x240 PPM is about 180 KB, which is
  noise next to a run that already writes a pack, but a millisecond-scale
  interval would not be.
- The live directory is scratch. It lives beside the run's output prefix, is
  never part of the pack, and nothing downstream may read it — a consumer would
  make the recording depend on the viewer again through the back door.
- The viewer now owns a CHR and palette decoder — NES knowledge in Python that
  the Core already has in C++. That duplication is the price of not perturbing
  the render path, and it is the first place to look when the sprite layer and
  the composed frame disagree.
- The viewer is the first thing in this project that shows a recording while it
  happens. Once it exists, the honest place to answer "did the run reach
  gameplay" is there, not in a post-hoc contact sheet.
