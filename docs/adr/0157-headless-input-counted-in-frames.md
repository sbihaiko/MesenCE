# ADR-0157: Headless input is counted in emulated frames, and the harness drives the core frame by frame

- Status: accepted
- Date: 2026-09-05
- Related: ADR-0013 (same axis, exporter side), ADR-0050, ADR-0153, ADR-0156, PRD Part A Phase 9 (F9.13, F9.14), `scripts/headless_record.cpp`, `scripts/bootstrap_auto_packs.sh`, `scripts/gameplay_probe.py`

## Context

`scripts/headless_record` drives a recording by the **host clock**. The core
runs on its own emulation thread under the frame limiter; the harness sleeps
in 50 ms steps and advances the input script when enough wall-clock seconds
have passed, with each step declared in seconds (`InputStep::seconds`, the
`input=<script>` parser). How many emulated frames a step covers is therefore
a function of host load: the same script, the same ROM and the same binary
produce a different number of frames per step on a loaded machine than on an
idle one.

That matters because the scripts are **menu navigation**, where a step is not
a duration but a position in a sequence. F9's per-game scripts encode exactly
that kind of knowledge: Punch-Out!! advances on Start alone (A or Right on the
title types into the PASS KEY field), and both Zeldas need SELECT — not the
D-pad — to move the heart on REGISTER YOUR NAME. One step landing early or
late derails every step after it, and the failure is **silent**: the recording
keeps running, capturing the wrong screen for the rest of its 300 s. Two packs
held 69 near-identical captures of a name-registration screen; another was
recorded entirely on a password screen while the batch printed `OK`.

F9.13 answers "did this recording reach gameplay?" *after the fact*, from a
pack on disk. That detector is worth keeping — it also catches a script that
was simply wrong — but it is a diagnosis of the symptom. The cause is that the
harness has no way to say "hold Start for 12 frames" and mean it.

ADR-0013 already rejected the host clock as a time source on the other end of
the same pipeline: exporter timing derives from an emulated 44100 Hz sample
counter, precisely so fast-forward, a breakpoint pause or a stalled host frame
cannot change what a capture means. Input is the same axis, unresolved.

The mechanics of driving the core externally are known rather than
speculative. The `libretro/MesenCE` fork does it, and its commit `41e0b517`
("remove additional frame of latency due to stale input") records the trap
that comes with it: refreshing the key manager is not enough, because the
frame reads the *control manager* — `GetControlManager()->UpdateInputState()`
has to run before `RunFrame()`, or the frame consumes the previous frame's
input. Its `Emulator` changes record the rest: when `Run()` is not executing,
`_frameLimiter` does not exist and `ProcessEndOfFrame` must tolerate that, and
`_console->GetControlManager()->ProcessEndOfFrame()` has to be called by hand.

**Non-goals.** This does not replace `gameplay_probe.py` (F9.13); the detector
stays. It does not change what a pack contains, nor any pack-format
precedence. It is not about emulation accuracy. It does not add movie
recording or playback.

## Decision

**1. The script's unit is the emulated frame, declared explicitly.** A line of
an `input=<script>` file is `<count><unit> <buttons>`, where `<unit>` is `f`
(frames) or `s` (seconds). A bare number is a **parse error**, not a default —
the existing scripts use bare numbers meaning seconds, and silently
reinterpreting `3` as three frames would corrupt every hand-tuned sequence in
the recorder library. Migration is appending `s` to each line; the per-game
scripts written by `bootstrap_auto_packs.sh` are regenerated in frames.

`s` is resolved to frames **at parse time**, using the region's nominal frame
rate (NTSC 60.0988, PAL 50.0070 — the `pal` flag already selects the region),
rounded to the nearest frame. After parsing, the harness knows only frames, so
a script's meaning never depends on host load regardless of which unit it was
written in.

**2. The harness drives the core frame by frame.** `headless_record` stops
sleeping against `steady_clock` and stops relying on the emulator's own `Run()`
loop. Per frame it applies the script's override for the current frame, then
steps exactly one frame, then advances its frame cursor. This requires, in
order:

- an InteropDLL entry point that runs a single frame, so the harness — not the
  frame limiter — decides when the next frame happens;
- `Emulator::ProcessEndOfFrame` tolerating a null `_frameLimiter`, which only
  exists while `Run()` is executing;
- `_console->GetControlManager()->ProcessEndOfFrame()` called explicitly on
  that path;
- the override applied through `GetControlManager()->UpdateInputState()`
  before the frame runs, never after — the stale-input frame of latency above.

The recording length argument (`<seconds>`) is likewise converted to a frame
count at startup, so a run is a fixed number of frames.

**3. The headless path is a runtime mode, not a compile-time one.** No
`#ifdef` in `Core/`. The libretro fork spreads `#ifdef LIBRETRO` through
`Emulator.{h,cpp}`, `KeyManager`, `SoundMixer`, `WaveRecorder` and
`VideoDecoder`; that cost is permanent and it means the headless harness and
the shipped GUI no longer exercise the same code. The core is one binary, and
the frame-stepping path is selected at runtime.

**4. Verification.** Recording the same ROM twice with the same script and the
same binary must produce byte-identical `auto/` output. That check is the
point of the slice — it is not obtainable today at any host load — and it is
what a regression here would break first. `Emulator::GetFrameCount()` gives
the harness the cross-check that its own frame cursor and the core's agree.

## Consequences

Recordings become reproducible: a pack is a function of (ROM, script, binary),
which is what the F9 goldens have been implicitly assuming. Scripts become
reviewable as sequences — "12 frames of Start" is a fact a reader can check
against a game's behaviour, where "0.2 s" was a guess about scheduling.

The costs are real. Every existing `input=` script and every `<Game>.play.txt`
in the recorder library has to be migrated (mechanical: append `s`), and the
parse error is deliberately noisy so none is missed silently. Driving frames
from the harness means the harness now owns pacing that the frame limiter used
to own, so a recording runs as fast as the host allows rather than in real
time — wall-clock run durations in existing docs and scripts stop being
predictive, and anything that assumed a 300 s recording takes 300 s needs
re-reading. The single-frame entry point is new public surface on the
InteropDLL, mirrored in the C# interop declarations like every other export.

This ADR decides the *harness*. Interactive playback in the GUI is untouched.

## Alternatives

**Keep the emulation thread and poll `Emulator::GetFrameCount()`**, applying
the next override when the counter reaches the step's target. Cheaper — no new
entry point, no `_frameLimiter` guard — and it removes the gross drift, since
a step would cover the frames it declares. Rejected because it does not
deliver the property the slice exists for: the override still lands one or two
frames off depending on when the polling loop wakes, so two runs of the same
script still produce different output and the byte-identical check in §4 is
unobtainable. It buys most of the robustness and none of the reproducibility.

**Use the existing movie system** (`Core/Shared/Movies`, `MesenMovie` /
`MovieRecorder`), which already stores input per frame and replays it
deterministically. Rejected as the authoring format: a movie is a recorded
binary artifact, not a text file a person writes and reviews, and producing
one means playing the game in the GUI. The F9 scripts' value is that they are
hand-written, diffable statements of what a game's menus need. The movie
system remains the right tool for capturing a long human play session, which
is a different job.

**Leave it as is and rely on F9.13.** Rejected: the detector reports that a
recording missed gameplay, but the batch has no way to fix it other than
re-running and hoping for a better schedule, and it cannot distinguish a wrong
script from a script that lost a race.
