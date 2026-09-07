# ADR-0167: A HUD-only capture seam answers "did a toast appear", without a renderer or a checksum on faded pixels

- Status: accepted (2026-09-07, by the user; PRD Part A, extends F9.15)
- Date: 2026-09-07
- Related: `Core/Shared/Video/FrameCapture.h` (F9.15, PRD Part A), ADR-0150 (Avalonia.Headless — the other axis of manual-check automation), `docs/validation/manual-validation-automation-plan.md` (wave 3, "What remains genuinely manual")

## Context

F9.15 gave `scripts/headless_record` an in-memory frame capture — `FrameCapture.h`'s `IsCaptureSizeValid`/`MeasureBorders`/`Checksum`, reached through `HeadlessCaptureFrame`/`HeadlessReadCapturedPixels` — and it closed several manual checks by turning "a human looks at a PNG" into an assertion. `docs/validation/manual-validation-automation-plan.md`'s wave 3 went through every remaining manual item and asked which of them that capture actually reaches. Most don't: a physical pad, subjective audio timbre, and the OS's native file picker are named as genuinely manual, for reasons that hold regardless of what capture exists. One item is different — **"the OSD toast appearing"** — because the reason it's manual is structural, not a wall: nothing captures the HUD at all, in any run.

Traced against the code rather than assumed:

- `VideoRenderer::RenderThread()` (`Core/Shared/Video/VideoRenderer.cpp`) is the only place `SystemHud::Draw` is called and `_emuHudSurface` is filled, and the entire body is gated on `if(_renderer)`. `scripts/headless_record.cpp` calls `InitializeEmu` with null window/viewer handles, so `_renderer` is `nullptr` in every headless run today (this is deliberate — no window, no sound, no input backend). Consequently the HUD is not merely uncaptured, it is **never rasterised** in the harness: `SystemHud::Draw` doesn't run, `_emuHudSurface.Buffer` stays null. F9.15's `CopyOutputBuffer`/`CaptureScreenshot` read `BaseVideoFilter::_outputBuffer`, the decode thread's product, which the HUD (a render-thread product, on a differently-sized surface) never touches anyway — so even a `_renderer`-driven run wouldn't put a toast in that buffer.
- `SystemHud` (`Core/Shared/Video/SystemHud.h/.cpp`) is pure software: `DisplayMessage` queues a `MessageInfo` (fixed 3000 ms lifetime), `Draw` emits `DrawString` calls into a caller-owned `DebugHud`, and `DebugHud::Draw` rasterises them into a plain `uint32_t*` ARGB buffer with no GPU, no window, no platform code. `SystemHud` is already constructed and registered as the global message sink in every run, headless included (`MessageManager::RegisterMessageManager` runs from the `Emulator`/`VideoRenderer` constructor chain, not from `_renderer`'s), and `_osdEnabled` defaults to `true` — the harness never disables it. `InteropDLL/EmuApiWrapper.cpp` already exports `DisplayMessage`, so a headless run can enqueue a deterministic toast with no new export.
- A precedent already composes exactly this, in production code, with none of the above obstacles: `VideoRenderer::ProcessAviRecording` builds a local `DebugHud`, calls `_systemHud->Draw` and `InputHud::DrawControllers` on it, and rasterises the result over a copy of the frame buffer — no `_renderer`, no render thread, no GPU. It proves a HUD composite is a same-thread, software-only operation reachable without touching `VideoRenderer.cpp:127`'s guard at all.
- Two clocks make a toast's pixels **not deterministic across runs** if captured naively: `MessageInfo::GetOpacity()` computes fade-in/fade-out from `std::chrono::high_resolution_clock`, and `DrawTurboRewindIcon` animates off a separate wall-clock timer. A raw `Checksum()` over a HUD surface containing a mid-fade toast would differ run to run for reasons that have nothing to do with whether the toast is there. Separately, `DrawPauseIcon` draws unconditionally while the emulator is paused, and `headless_record` pauses before every capture (F9.15's own pattern) — so a naive "is the HUD surface non-blank" oracle would report `true` on every run, toast or not, once paused.

Non-goals: this ADR does not composite the HUD onto the *filtered* output frame (post rotate/scale/scanline) — that pixel-perfect picture is a second, harder problem (reconciling `GetEmuHudSize`'s surface with `BaseVideoFilterCapture`'s filtered dimensions) that no PRD row currently needs; it does not touch `VideoRenderer`'s render-thread path, `_renderer`, or any platform renderer; it does not change `SystemHud`'s toast duration, fade curve or pause-icon behaviour — those are product decisions, not this ADR's.

## Decision

**A HUD-only capture, modelled on `ProcessAviRecording`, exposed the same way F9.15 exposed the frame capture — and answered with a blank/non-blank oracle, not a raw checksum.**

1. **`Core/Shared/Video/SystemHud`** gains a way to draw itself into a caller-owned buffer without a `VideoRenderer` render pass: an accessor (on `VideoRenderer` or `Emulator`, whichever keeps `SystemHud` unique_ptr ownership where it already is) that, given a target size, builds a local `DebugHud` exactly as `ProcessAviRecording` does, draws the system HUD into it under `_hudLock` (the same lock `RenderThread` takes — a headless caller must not skip it, since a `_renderer`-driven run could theoretically coexist), and hands back the raw `uint32_t*` buffer plus its dimensions. `DrawInputHud`/`DrawScriptHud` are out of scope — this is the system-message layer only, the one `DisplayMessage`/toasts go through.
2. **`FrameCapture.h`'s existing primitives are reused as-is**: `MeasureBorders` and its `IsBlank` field become the toast oracle — a HUD surface with no active message is uniformly transparent (`IsBlank == true`); a surface with a toast has a non-uniform region (`IsBlank == false`), independent of exactly which fade phase the opacity animation is in. `Checksum()` is still computed and printed for parity with the frame-capture contract, but the pass/fail decision in test code is `IsBlank`, never the checksum — the checksum is diagnostic only, because opacity's wall-clock fade makes it legitimately different between two otherwise-identical runs.
3. **New headless exports, same shape as F9.15's**, added to `InteropDLL/EmuApiWrapperHeadless.cpp` (comment there already flags it as the file for this kind of seam): `HeadlessCaptureHud(width, height, outWidth, outHeight, outPixelCount)` mirrors `HeadlessCaptureFrame`'s two-call pattern (measure, then `HeadlessReadCapturedHudPixels(outPixels, maxPixels)` copies) — the caller supplies the target size (typically the base frame size) rather than reading a filter's output size, since there is no filter in this path.
4. **`scripts/headless_record`'s `capture` flag gains a third output line**, added after the two F9.15 already prints, so the existing two-line contract `bootstrap_auto_packs.sh` and other consumers already parse is untouched:
   ```
   capture hud: <W>x<H> checksum=0x%08X blank=<0|1>
   ```
   A caller wanting to assert "a toast appeared" calls the existing `DisplayMessage` export before the capture point and checks `blank=0`; asserting "no stray toast" checks `blank=1` with none queued.
5. **Options considered and rejected, for the record:**
   - *Composite the HUD onto the filtered frame output* (frame + HUD in one buffer, pixel-perfect to what a player would see): rejected as this ADR's scope because it inherits the opacity non-determinism *and* requires reconciling two independently-sized/scaled surfaces (`GetEmuHudSize`'s frame-relative size vs. `BaseVideoFilterCapture`'s post-filter dimensions) for no PRD row that currently needs pixel fidelity — the blank/non-blank question is all `docs/validation/manual-validation-automation-plan.md`'s wave-3 residue asks for. Left as a follow-on if a future slice needs the composited picture.
   - *Register a real `SoftwareRenderer` (or a new null renderer) in the harness* to let `VideoRenderer.cpp`'s existing `if(_renderer)` path run unmodified: rejected — it starts the render thread (a 32 ms `_waitForRender` loop), couples the capture to that thread's timing instead of the caller's own frame, and buys no fidelity `ProcessAviRecording`'s same-thread pattern doesn't already give for free. More moving parts for the same answer.

## Consequences

- Closes the last "genuinely manual, but structural rather than a wall" item wave 3 named: "the OSD toast appearing." F6.5's file picker, subjective audio and I.2/I.3's hardware needs are unaffected — they stay manual for the reasons already on record.
- `SystemHud`/`DebugHud` gain one more caller of their existing draw path; no behaviour change to what a real render pass does. The pause-icon and turbo/rewind-icon caveats are not fixed by this ADR — a test using this seam to assert "no toast" must not do so while paused (or must crop the pause icon's known corner out of `MeasureBorders`'s region), and a test asserting "toast present" should avoid the icon's corner for the same reason. This is stated here so a future test author does not rediscover it as a flaky failure.
- Three more DLL exports (`HeadlessCaptureHud`, `HeadlessReadCapturedHudPixels`, `HeadlessSetOsdEnabled`) and one more printed line in `headless_record`'s `capture` output — additive, in the same place F9.15 put its own two lines, so no existing consumer's parsing breaks.
- Still not solved by this ADR: a pixel-perfect "what would the player actually see" composite (frame + HUD, correctly scaled). If a slice ever needs that, it is a second decision built on top of this one, not a silent extension of it.

## Revision (2026-09-07, implementation)

Verifying the seam against a real recording surfaced two obstacles the original
Decision's caller contract did not foresee, and the harness gained two small
additions to get past them. The capture core is unchanged — `CaptureSystemHud`,
`MeasureBorders`/`IsBlank` as the oracle, and the two-call exports are exactly
as decided. What changed is the *state* the harness captures in:

1. **The game-loaded toast is always resident, not just the pause icon.** Every
   `LoadRom` enqueues a "[console] romfile" toast (`Emulator.cpp`, the `NTSC`/
   `PAL` model-name display). It only ages out via `SystemHud::UpdateHud`, which
   runs on running frames, and `headless_record` parks the emulator within a few
   frames of load — so the toast survives the whole short run. A HUD capture
   therefore read non-blank whether or not a message was queued, and `blank=1`
   was unreachable. Fix: the harness uses `MessageManager`'s existing OSD gate
   as a queue-hygiene switch — a new thin export, `HeadlessSetOsdEnabled(bool)`
   (`InteropDLL/EmuApiWrapperHeadless.cpp`, marshaling one bool over
   `MessageManager::SetOptions`, which also resets `outputToStdout` to `false`,
   the harness's state), is set `false` before `LoadRom` so the load toast goes
   to the log instead of the queue, and set `true` for the single instant a
   `hud-message=` run enqueues its own toast. With the OSD off, every capture
   run (including F9.15's, which never read the HUD) stays fast and its
   `blank` line reads truthfully.
2. **The capture runs while the emulator is running, not on the paused F9.15
   frame.** `SystemHud::Draw` paints the pause icon on every paused frame — the
   caveat this ADR's Consequences already named — so a paused capture could
   never read `blank=1`. The harness therefore takes the HUD capture right after
   `Resume()` (the run's pause latch is consumed, so the emulator runs until a
   re-armed `HeadlessSetPauseFrame` parks it again), after the deterministic
   frame capture and its two lines, which are untouched.
3. **A short settle after the resume.** A capture taken in the first instants
   after `Resume()` occasionally missed the just-queued toast (observed ~1/3 of
   runs with no settle, 0/N with one) — the same decode-thread transient the
   frame capture's own 200ms settle drains. `headless_record` sleeps 100ms after
   the resume when a toast was queued (comfortably inside the toast's 3000ms
   lifetime; the no-message baseline needs no settle). A side effect: by capture
   time the toast's 100ms fade-in is complete, so the checksum is deterministic
   too, though `blank` remains the oracle.

Verified against `roms/Zelda.nes` (real `Emulator`, no `_renderer`): a
`capture` run with no `hud-message=` reads `capture hud: ... blank=1` on 5/5
runs with an identical empty-surface checksum; the same run with
`hud-message=Headless|toast de teste` reads `blank=0` on 20/20. The two
pre-existing `capture:`/`capture borders:` lines keep the same deterministic
frame checksum in both, so F9.15/`accuracy_compare.py` consumers are unchanged.
