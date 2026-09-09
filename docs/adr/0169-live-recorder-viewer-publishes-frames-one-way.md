# ADR-0169: The recorder publishes its frames one way, and the live viewer never blocks the run

- Status: accepted — implemented (uncommitted): the `live=<ms>` tap and the
  sprite-layer record in `scripts/headless_record.cpp`, the viewer
  `scripts/record_viewer.py`, and the interactive producer
  `Core/Shared/LiveFrameRecorder` + the Tools-menu toggle (section 4). The
  commit awaits human review.
- Date: 2026-09-08
- Updated: 2026-09-08 — the sprite-layer read channel switched from the
  debugger-based `GetMemoryState` to direct console exports under
  `Emulator::Lock()` (Context bullet 3, Decision 2, Consequences bullet 1); the
  record shape and the measured hold cost now match the implementation.
- Updated: 2026-09-08 — the viewer may launch and stop `headless_record`
  itself, as a subprocess it controls (Decision section 3, Consequences
  bullet 6). It never writes into `<prefix>-live/`; it only owns the child
  process's lifecycle.
- Updated: 2026-09-08 — the interactive emulator is now the second producer
  (`LiveFrameRecorder`, Decision section 4) and supersedes the viewer-launch
  panel of section 3: the viewer no longer starts processes, fields, or knows a
  ROM; it auto-attaches by convention to the emulator's live slot.
- Updated: 2026-09-08 ("capture every layer") — both producers now also read
  the background layer under the same `Lock()` hold as the sprite layer:
  `nametables.bin` (the mapper-resolved `$2000-$2FFF` bytes) and
  `background.json` (pattern table, mask/enable bits, and loopy "t" +
  fine X — the scroll the game wrote, not loopy "v", which has already scanned
  the whole frame by an end-of-frame boundary). The viewer reconstructs the
  background from the captured scroll and nametable bytes, and multiplexes it
  with the sprite layer using the 2C02's own priority rule (front sprites
  always win; a behind-background sprite only shows through a transparent
  background pixel), so its reconstruction pane is a real composite reconstruction,
  not sprites drawn over a plain backdrop. Verified against two live NES
  captures (Mega Man 3's title screen, Zelda's file-select screen): 98.7-99.3%
  of native pixels are byte-identical to the emulator's own composed frame,
  and the two panes are visually indistinguishable side by side. The residual
  difference is the same gap section 2 always disclosed: a single end-of-frame
  read cannot see the PPU's 8-sprites-per-scanline limit or a mid-frame scroll
  split. Recordings from before this update still publish sprites-only; the
  viewer falls back to the old backdrop-only rendering for them.
- Updated: 2026-09-08 ("MMC2/MMC4 CHR-latch") — Mike Tyson's Punch-Out
  (mapper 9, and mapper 10/MMC4 by inheritance) swaps a 4KB CHR bank per
  pattern-table half mid-frame via a tile-index latch (`BaseMapper::
  HasChrBankLatch`, overridden only in `MMC2`): fetching tile 0xFD selects
  that half's "FD" bank, fetching tile 0xFE selects its "FE" bank, and the
  game exploits this to draw more graphics (e.g. Tyson's boxer portrait) than
  fit in the console's CHR-ROM at once. A single end-of-frame `chr.bin` read
  only ever holds whichever bank each half's latch last resolved to — wrong
  for any tile drawn earlier in the frame under the other bank, which is what
  "não vejo o player1, não vejo as fontes" (image capture, this session)
  turned out to be for this mapper specifically; every other mapper is
  unaffected. Both producers now also publish, only when
  `BaseMapper::HasChrBankLatch()` is true: `chrfull.bin` (the raw,
  latch-independent CHR-ROM) and `chrlatch.json` (each half's two bank
  numbers + the page size). The viewer walks the frame in the 2C02's own
  fetch order — a row's background tiles left to right, then that row's
  up-to-8 visible sprites in OAM order (the hardware's own per-scanline
  sprite cap) — updating each half's latch on every 0xFD/0xFE fetch exactly
  as `MMC2::NotifyVramAddressChange` does, and drawing every tile with
  whichever bank the latch held at that fetch (`build_planes_with_chr_latch`
  in `scripts/record_viewer.py`). The starting latch value per half is a
  guess (`deduce_initial_chr_latch`, from comparing chr.bin against the two
  candidate banks) rather than a proof, but the latch assignment is an
  unconditional overwrite, never a toggle, so a wrong guess self-heals at
  that half's first trigger fetch in the frame and is exactly right when
  there is no such fetch. A related, pre-existing, unrelated-to-the-latch bug
  surfaced during this diagnosis and is fixed alongside it: both producers
  had copied `Mask.BackgroundMask`/`Mask.SpriteMask` verbatim into the wire
  fields `BackgroundLeftColumnClip`/`LeftColumnClip`, but those PPU mask bits
  are a "show in the leftmost 8 pixels" flag (true = shown), the opposite
  polarity of what the wire field names — the assignment is now inverted at
  the producer so the field means what it says. Verified against a live
  Punch-Out capture (its "Mike is waiting for your challenge" portrait
  screen): 85.54% exact-pixel match before either fix, 92.15% after both. The
  residual is not a capture gap: the composite frame carries color values no
  entry of the run's own 64-color palette can produce (e.g. `(47,61,42)`),
  meaning Mesen's default NES video pipeline blends pixels (an NTSC-style
  composite artifact) that a palette-indexed reconstruction cannot and does
  not try to reproduce — the same category of disclosed gap as the
  8-sprites-per-scanline limit.
- Updated: 2026-09-08 ("frame/state capture race") — a batch run of the
  composite-vs-reconstruction comparison across 30 NES ROMs (per the /goal
  "testar as duas telas do player por similaridade para todas as ROMs")
  surfaced a second, generalizable bug distinct from the CHR-latch and
  mask-polarity ones above: both producers captured the composite pixels
  (CaptureScreenshot/HeadlessCaptureFrame) before taking Emulator::Lock() for
  the PPU/OAM/palette/VRAM read, instead of after. Lock() is what parks the
  emulation thread at an end-of-frame boundary (Consequences bullet 1);
  reading the pixels first and locking afterwards left a window in which the
  console could render one or more further frames before the state read, so
  the two halves of one published snapshot could describe two different
  frames outright. Symptoms scaled with how much changes frame to frame:
  Super Mario Bros. briefly showed the reconstruction's backdrop color from
  the frame after the composite's (a fast palette-cycle title screen), and
  Golf showed the reconstruction on a menu screen while the composite had
  already advanced to the course view — a full scene change, not a color
  glitch. It also explains what "nem todos os sprites estao com borda" turned
  out to be: a sprite's OAM entry and the composite pixels it is outlined
  against could belong to different frames, so a real, visible sprite's
  bounding box would land on the wrong position or not be drawn at all;
  re-verified on Punch-Out after the fix (every visible face/logo sprite in a
  fresh capture gets its box, and the two sprites that legitimately don't are
  the mapper's own 0xFD/0xFE latch-trigger dummies, invisible by design).
  Fixed by reordering both producers to lock first: Core/Shared/
  LiveFrameRecorder.cpp's CaptureSnapshot now calls _emu->Lock() before
  CaptureScreenshot, not after; scripts/headless_record.cpp's
  CaptureLiveSnapshot has no direct Emulator* (it talks to the DLL through the
  Headless* export surface), so two new exports, HeadlessLockEmulator/
  HeadlessUnlockEmulator (thin wrappers over _emu->Lock()/Unlock(),
  InteropDLL/EmuApiWrapperHeadless.cpp), let it park the thread around both
  HeadlessCaptureFrame and HeadlessCaptureNesSpriteLayer in one hold;
  SimpleLock is reentrant per thread (_lockCount), so this nests safely inside
  HeadlessCaptureNesSpriteLayer's own internal Lock/Unlock without
  deadlocking. Measured effect across the 30-ROM batch (mep-off, to isolate
  the reconstruction engine from HD-pack visual substitution — see below):
  Super Mario Bros. 43.09% → 99.80%, Golf 12.85% → 37.65%, Mike Tyson's
  Punch-Out 92.15% → 98.29%; 24 of 30 ROMs now land at 97%+ (many 99-100%),
  up from a batch where several titles were under 2%.
- Updated: 2026-09-08 ("HD packs are not a reconstruction target") — the same
  batch run's worst scores before the race fix (Castlevania 0.89%, Donkey Kong
  0.01%, Metroid 0.00%, Mega Man 1.82%, The Legend of Zelda 0.18%, Contra
  39.83%) turned out not to be reconstruction bugs at all: ADR-0146 auto-loads
  every registered community HD pack, so the composite frame these titles
  render is community-drawn replacement art (visually confirmed — e.g.
  "METROID -HIGH DEFINITION-", "CONTRA 80's Reimagined By: Tastic"), which the
  reconstruction engine has no way to know about from CHR-ROM/VRAM alone: it
  is not the pixels the console is generating, so a palette-indexed
  reconstruction of the original tiles will never match it. There is no data
  channel that could carry a substituted tile back to a reconstruction: the
  matcher (`HdNesPack::GetMatchingTile`) is stateful and runs on the video
  thread, and the pack's art is not derivable from any PPU state the capture
  reads. So the recorder publishes the *condition* instead of guessing at the
  pixels: `LiveSnapshot::HdPackActive` (from `NesConsole::IsHdPackVideoActive`,
  the same `_hdData && HasVideoContent()` test that swaps in `HdNesPpu`) goes
  out in status.json from both producers, and record_viewer.py replaces its
  reconstruction caveat with an explicit "substitution is ON, these two panes
  are not comparable, turn Enable HD Packs off" rather than showing a score
  that reads as a fidelity failure.
- Updated: 2026-09-08 ("hdpack-off is the switch, not mep-off") — measuring
  reconstruction fidelity needs substitution off at the gate the player itself
  uses, `NesConfig::EnableHdPacks` (checked first in
  `NesConsole::LoadHdPack`). `mep-off` only takes MEP-installed packs out of
  discovery; a loose `HdPacks/<rom>/` pack (MEP-v1 §5.1) still loads and still
  replaces pixels, so it is an approximation of the player's own switch, not
  the switch. headless_record gained `hdpack-off` for exactly that, and the
  30-ROM batch re-run with it — each line asserting the run's own published
  `hdPackActive=false`, so "substitution really was off" is measured rather
  than assumed — lands **every one of the 30 ROMs at 98.10% or better**
  (mean per-pixel RGB delta 3.6-6.3 of 765 on the worst six). The titles that
  had scored 0-2% with packs auto-loaded now read Castlevania 99.59%, Donkey
  Kong 99.95%, Metroid 99.85%, Mega Man 100.00%, The Legend of Zelda 98.10%.
  Per-pixel diff maps on the worst three attribute the whole residual to
  animation drift between the composite poll and the state read (Zelda II's
  twinkling stars and cycling sword glow, Bubble Bobble's drifting bubble
  sprites) or to the MMC2 latch path picking a neighbouring bank for a few
  portrait/logo tiles (Punch-Out) — adjacent-palette-entry swaps along tile
  edges, not a layer or priority error.
- Updated: 2026-09-08 ("mid-frame raster splits are still out of reach") — of
  the 30-ROM batch, six titles remain well below the rest even after the two
  fixes above, and diagnosis traced every one to the same disclosed gap this
  ADR has named since section 2: a single end-of-frame snapshot cannot see a
  mid-frame PPU/mapper register write. Golf and Zelda II (status-bar split:
  scroll changes partway down the screen, a fixed HUD above a scrolling
  playfield below) reconstruct the top half of the screen correctly and go
  black below (or vice versa); Life Force/Super Mario Bros. 3's title screen
  (a mid-frame CHR-bank or nametable-pointer switch — the captured
  nametables.bin genuinely holds tile index 0 for the region in question,
  confirming the read is faithful, just to a snapshot the game already moved
  past) go blank in exactly the region the game redraws with a second raster
  pass; Gauntlet's title art and Lemmings' title screen (a mid-frame CHR-bank
  switch reusing the same tile indices for font glyphs in one bank and
  picture art in another) show scrambled tiles for the same reason. Seeing
  this correctly would need capturing every relevant register write with its
  scanline/cycle timestamp for the whole frame — a materially bigger capture
  format than this ADR's single end-of-frame read, and out of scope for this
  pass. Left as a documented, disclosed limitation alongside the
  8-sprites-per-scanline cap and the NTSC-blend residual.
- Updated: 2026-09-08 ("Record opens the viewer, and the slot re-targets per
  ROM") — three changes to the interactive producer of section 4, all pulling
  in the same direction: whoever starts a live recording should get the picture
  without a second, manual step. (a) **The menu is a submenu, not a toggle.**
  The Tools entry now reads "Live Recorder (viewer)" with Record / Stop /
  Open Viewer children, the same shape as the Sound, Video and Music recorders
  next to it, instead of the one-off dynamic-text item that flipped its own
  caption. (b) **Record starts the recorder and opens the viewer.** This
  narrows section 4's last bullet and section 3's "it never launches a
  process": the *viewer* still launches nothing and still auto-attaches by
  convention with zero fields — it is now the *emulator* that spawns
  `scripts/record_viewer.py` as a detached process, once, when a human asks to
  record. The script is not bundled with the app, so it is located by walking
  up from the executable and the working directory (`UI/Logic/
  RecordViewerLocator.cs`, host-free per ADR-0123, with unit tests), overridable
  by `MESENCE_RECORD_VIEWER`, and tried against each plausible python command
  for the platform. Every failure to find python or the script is logged and
  shown as a message, and explicitly does not touch the recording: the
  protocol stays one-way (section 1), so a viewer that never starts costs the
  run nothing. `Open Viewer` exists for the case where the human closed it.
  (c) **The record carries its ROM, and the slot re-targets when the ROM
  changes.** A single convention slot (section 4) is reused by every session,
  so nothing in it told one game from the next; `status.json` gained a
  `"rom"` field (`ComposeStatusJson`'s last argument, escaped through
  `ComposeJsonString` — a ROM file name can hold a quote or a backslash), and
  both producers publish it. The interactive recorder cannot read
  `Emulator::GetRomInfo()` from its own thread — it returns a reference to a
  string `InternalLoadRom` reassigns — so the UI *announces* the name across
  interop (`LiveRecordingSetRom`, called on `GameLoaded` and cleared on
  `EmulationStopped`) and the recorder compares/copies it under a lock. A
  changed name is then treated exactly like a fresh start: the slot is cleared,
  the palette latch and log-once flags reset, the wall clock restarts. That
  matters because the viewer keys its reconstruction paths on *file presence*
  (`chrfull.bin`/`chrlatch.json` exist only for a latch mapper, section 4's
  MMC2 note), so a leftover file from the previous ROM would silently select
  the wrong decode path; the viewer independently drops all frame caches and
  retitles itself on a `"rom"` change. Alternative rejected: a per-ROM
  subdirectory, which would give the viewer a field to fill again and undo the
  zero-field attach.
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
live directory, draws what it finds, and writes nothing into it. Given no run
in progress it says so rather than failing.

> Superseded in part by section 4 (interactive producer): the launch panel below
> was the first design. It is removed — the viewer no longer launches a
> recorder, and section 4 is the reason. It is kept here to record the trade
> that was walked back, and because Attach-to-a-path (the last bullet below)
> still stands unchanged.

The viewer may also launch `headless_record` itself, as a control panel with
traditional recorder buttons (⏺ Record / ■ Stop) over a small form — ROM,
duration, an optional input script, the live-publish interval, a realtime
checkbox — instead of requiring a separate terminal command. This does not
change the protocol of section 1: the viewer still never writes a byte into
`<prefix>-live/`, and the recorder still never blocks on, or even knows about,
a reader. What is new is process lifecycle, owned entirely by the viewer:

- **Record** derives an output prefix under `runs/viewer-launched/` from the
  ROM name and a timestamp (so two launches never collide), builds the same
  command line a human would type, and starts it with `subprocess.Popen`. The
  live directory the viewer polls switches to that run's `<prefix>-live/`.
- **Stop** sends the child process `SIGTERM` and nothing else.
  `headless_record` has no graceful-shutdown handler for it, so this kills the
  run outright — which is the same outcome as a crash from the viewer's
  perspective, and section 3's crash handling below covers both with one
  code path rather than two.
- The viewer keeps polling the live files after the child process exits. If
  `status.json` never reached `done: true`, the last published frame stays on
  screen and the status bar reports the run as interrupted (crash, a bad ROM
  argument, or a deliberate Stop) rather than clearing to "no run in
  progress" — the frame before a crash is exactly what helps diagnose it, so
  it is not thrown away. Reaching `done: true` before exit is reported as a
  normal finish, same as today.
- Attaching to a recording the viewer did not launch keeps working
  unchanged: the live-directory field stays a plain path a user can type or
  point elsewhere, independent of the launch form, so several viewers can
  still watch the same run (section 1) and a script-launched run started
  from a terminal is still watchable.

### 4. The interactive emulator is the second producer — by convention, not by form

The launch panel of section 3 existed to remove the need for a terminal
command. It is itself removed by a better answer: the **emulator already has
the ROM open and the controller in hand**, so the producer moves into it. A
`LiveFrameRecorder` (`Core/Shared/LiveFrameRecorder.h/.cpp`), owned by
`Emulator` (`GetLiveFrameRecorder()`) like `VideoRenderer`/`SoundMixer`,
publishes the same wire format to a **single convention slot**,
`<HomeFolder>/LiveRecording` (`ConfigManager.LiveRecordingFolder`), while a
human plays. A Tools-menu toggle starts and stops it; nothing is typed.

Decisions that follow:

- **The recorder runs on its own timer thread**, not on the video decode
  thread. The NES sprite-layer read parks the emulation thread with
  `Emulator::Lock()` for an instant (section 2's channel); doing that from
  `VideoRenderer`'s decode thread would introduce an unmeasured wait into the
  render pipeline. A dedicated thread keeps the risk identical to the
  already-measured headless case (Consequences bullet 1). `StartRecording`
  spawns and `StopRecording` joins it; destruction order in `Emulator` puts
  `_liveFrameRecorder` before the `VideoDecoder`/settings it reads.
- **There is no target frame.** A scripted run has `targetFrames`; a human-run
  session ends when the human says so. The recorder writes
  `ComposeStatusJson(..., targetFrames=0, ...)`, which the viewer renders as
  `frame N · live` rather than `frame N/0`, and StopRecording writes one final
  `done: true` status — the interactive equivalent of a scripted run parking on
  its target.
- **The interval is fixed** (250 ms in the menu toggle) — one less field.
- **The sprite layer is NES-only.** `LiveFrameRecorder::CaptureSnapshot`
  publishes frames for any console; the OAM/palette-RAM/CHR record and the
  one-time `palette.json` (captured from the NES config's `UserPalette`, the
  base 64-color table the 2C02 filter copies verbatim at zero emphasis) only
  for a `NesConsole`. GB/SMS/GG live sessions are frame-only, as in
  `headless_record`.
- **The viewer auto-attaches by convention.** With no argument it watches
  `<HomeFolder>/LiveRecording` (mirroring the C# home-folder rule in Python),
  so opening it beside a running emulator shows the live session with zero
  fields. The path box stays only as the manual override of section 3's last
  bullet — to watch a terminal-launched `<prefix>-live/` of `headless_record`.
  It never launches a process now, so section 3's subprocess machinery is gone.

## Consequences

- The debugger-based read path is unusable rather than merely expensive:
  `GetMemoryState`/`GetPpuState` attach the debugger, and a headless run under
  a live debugger never parks on its target frame (`HeadlessInputEngine`
  `ApplyFrame` logs "not pausing" and returns when `IsDebugging()`), so the run
  would never end. The realized channel attaches no debugger: both producers
  read under `Emulator::Lock()`, which parks the emulation thread at an
  end-of-frame boundary (it spins in `WaitForLock` with `_threadPaused` set)
  without touching the run's own pause/stop machinery — the scripted run still
  stops on its declared frame, and the interactive run never stalls under a
  human. The cost of that hold is what this draft originally asked to measure;
  measured on a 5-second NES smoke, a 200 ms live tap added ~0.1 s of wall
  clock over the plain run (1.0 s vs 0.9 s) — noise against the 2-minute
  budget.
- The interactive producer is a new Core source pair,
  `Core/Shared/LiveFrameRecorder.{h,cpp}`, registered in `Core.vcxproj` and its
  filters, so ADR-0007 is triggered and re-run (it passes). `Emulator` owns one
  instance (`GetLiveFrameRecorder()`) and exposes it to the UI through
  `InteropDLL/RecordApiWrapper.cpp` (`LiveRecordingStart/Stop/IsRecording`) and
  `UI/Interop/RecordApi.cs`, mirroring the AVI/WAV recorder exports.
- The live directory is still scratch and single-slot under the home folder:
  `<HomeFolder>/LiveRecording`. The C# side derives it from the same
  `ConfigManager.LiveRecordingFolder` the viewer mirrors, so the ROM name, the
  interval and the path never appear in either UI — the "ROM open in the
  emulator" and "the joystick in the human's hand" are the only inputs the
  recorder needs. Unlike a scripted run there is no `<prefix>-live/` beside a
  named output prefix; the slot is deliberately disposable and one per session.
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
- Launching from the viewer makes it, for the first time, a thing that can
  start a child process rather than only read files. That is still a narrow
  capability — one command line, one process, killed with one signal — and
  the boundary that matters (no bytes written into `<prefix>-live/`, no
  dependency of the recorder on the viewer being open) is unchanged. Runs
  launched this way land under `runs/viewer-launched/`, not the run
  directories a task or a script names on purpose, so they are easy to find
  and easy to ignore. **Removed with the launch panel (section 4 supersedes
  it)** — the viewer owns no child process any more; the process that records
  is the emulator itself.
