# ADR-0157: Headless input is counted in emulated frames, resolved from inside the frame

- Status: accepted
- Date: 2026-09-05
- Amended: 2026-09-05
- Related: ADR-0158 (runtime mode, not compile-time — relies on §3), ADR-0162 (the accuracy harness drives input through this contract), ADR-0013 (same axis, exporter side), ADR-0050, ADR-0153, ADR-0156, PRD Part A Phase 9 (F9.13, F9.14), `scripts/headless_record.cpp`, `scripts/bootstrap_auto_packs.sh`, `scripts/gameplay_probe.py`

## Amended 2026-09-05

Section 2 originally required the harness to **drive** the core frame by frame:
a single-frame InteropDLL entry point, a null-`_frameLimiter` guard in
`ProcessEndOfFrame`, a hand-called `ControlManager::ProcessEndOfFrame`, and the
override pushed through `UpdateInputState()` before each frame. Reading
`zerkz/MesenCE`'s `Core/Shared/InputOverrideProvider.{h,cpp}` — the prior art
the PRD's fork survey pointed at — showed that the property the slice exists
for is already reachable from inside the core, at a fraction of the surface.

An `IInputProvider` registered on the emulator has `SetInput()` called from
*inside* the frame, once per frame, on the emulation thread. A provider that
holds the **whole script in absolute frame numbers** therefore answers "which
buttons are held on frame N" as a pure function of the script and
`Emulator::GetFrameCount()` — no external thread has to wake up on time, or at
all. The harness does not need to own pacing to own the result. Section 2 below
is rewritten to that design; the frame-stepping approach moved to Alternatives
as rejected-for-now, because it costs new InteropDLL surface and a change to
the threading model to buy a property the provider already gives.

Sections 1, 3 and 4 are unchanged, apart from one dangling phrase in section
3 ("the frame-stepping path" -> "the headless path"); the rule it states — no
`#ifdef` in `Core/` — is untouched.

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

**2. The script is resolved from inside the frame, and the run ends on an
absolute frame count.** A `HeadlessInputProvider` — an `IInputProvider` plus an
`INotificationListener` — holds the parsed script and is registered on the
emulator. `BaseControlManager::UpdateInputState()` calls `SetInput()` on it once
per frame, on the emulation thread (`NesPpu` at `InputScanline`,
`SmsConsole`/`Gameboy` at end of frame), so the provider resolves the step
covering `Emulator::GetFrameCount()` and applies it. Concretely:

- buttons are resolved **by name** through `BaseControlDevice::
  GetKeyNameAssociations()` and set with `SetBitValue`, so one script drives a
  NES, GB and SMS pad without knowing which is loaded;
- `SetInput` returns `false`, so the script **overlays** physical input instead
  of replacing it;
- the provider **re-registers itself on `ConsoleNotificationType::GameLoaded`**.
  A new console — and with it a new control manager, holding no providers — is
  created on every game load. That is the structural root of our documented
  "`input=` is silently a no-op" trap;
- the run's **end** goes through the same hook: the provider is given an
  absolute stop frame and calls `Emulator::Pause()` from inside the first frame
  that reaches it. `Pause()` only sets a flag, so the emulation thread parks
  after finishing exactly that frame. A host timer that fires whenever the OS
  gets round to it would have covered a host-dependent number of frames;
- the same mechanism fixes the *start*: the harness stops the run on frame 1
  before starting any recorder, so what a recording is started on is a fixed
  frame rather than "whatever the emulation thread reached while this thread
  was calling into the DLL".

The harness therefore never drives frames. It parses, hands the provider one
list of absolute ranges, resumes, and waits. The recording length argument
(`<seconds>`) is converted to a frame count at startup, so a run is a fixed
number of frames.

Because nothing in the result depends on when frames happen, **speed is a free
variable**: the frame limiter is turned off (`EmulationSpeed = 0`), which makes
a 300 s recording finish in a fraction of that without changing a byte of its
output. A `realtime` flag puts the limiter back for anyone who wants to watch
one go by.

One non-obvious consequence found while verifying section 4: covering the same
frames is necessary but not sufficient. `RamState::Random` power-on RAM makes a
game that reads uninitialised memory take a different path, and two runs over
identical frames still differ. The harness zeroes it, as the core's own
deterministic replay harness already does (`RecordedRomTest::Run`).

Deterministic power-on RAM is therefore **part of this decision, not an
implementation detail**, and it has a cost worth stating plainly: a game that
seeds its RNG from uninitialised memory now behaves *identically in every
recording*. Where a recording library previously got some free variety by
running the same ROM more than once — different enemy patterns, different
random level furniture, and therefore different tiles captured — it now gets
the same run every time. Variety has to come from the script instead. If a
future slice wants spread across recordings, the way to get it is an explicit,
recorded seed (a `ramseed=` argument selecting a fixed pattern per run), never
a return to `RamState::Random`, which would trade the reproducibility of
section 4 away to buy it.

**3. The headless path is a runtime mode, not a compile-time one.** No
`#ifdef` in `Core/`. The libretro fork spreads `#ifdef LIBRETRO` through
`Emulator.{h,cpp}`, `KeyManager`, `SoundMixer`, `WaveRecorder` and
`VideoDecoder`; that cost is permanent and it means the headless harness and
the shipped GUI no longer exercise the same code. The core is one binary, and
the headless path is selected at runtime.

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
parse error is deliberately noisy so none is missed silently. Turning the frame
limiter off means a recording runs as fast as the host allows rather than in
real time — wall-clock run durations in existing docs and scripts stop being
predictive, and anything that assumed a 300 s recording takes 300 s needs
re-reading. The new InteropDLL surface is four thin exports over the provider
(load script, set stop frame, read either frame count); no core invariant is
relaxed and no thread changes owner.

This ADR decides the *harness*. Interactive playback in the GUI is untouched.

## Alternatives

**Drive the core frame by frame from the harness** — the design this ADR
originally decided (see the amendment note): a single-frame InteropDLL entry
point, `Emulator::ProcessEndOfFrame` tolerating the null `_frameLimiter` that
only exists while `Run()` executes, `_console->GetControlManager()->
ProcessEndOfFrame()` called by hand, and the override pushed through
`UpdateInputState()` before each frame (the stale-input frame of latency the
libretro fork's `41e0b517` records). Rejected for now: it buys the same
property the provider already gives — input resolved against the core's frame
counter, and a run that ends on an absolute frame — at the cost of new public
InteropDLL surface, a guard on a core invariant that holds today, and a
threading model where the harness owns pacing. It stays the right answer if we
ever need to *interleave* work between frames (read memory at frame N, decide
frame N+1), which nothing here does.

**Keep the emulation thread and poll `Emulator::GetFrameCount()`**, applying
the next override when the counter reaches the step's target. Cheaper — no new
entry point, no `_frameLimiter` guard — and it removes the gross drift, since
a step would cover the frames it declares. Rejected because it does not
deliver the property the slice exists for: the override still lands one or two
frames off depending on when the polling loop wakes, so two runs of the same
script still produce different output and the byte-identical check in §4 is
unobtainable. It buys most of the robustness and none of the reproducibility.
Note that this is *polling from outside*; §2 as amended resolves the script
from inside the frame, which is what removes the last frame of slack.

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
