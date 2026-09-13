# ADR-0181: The recorder keeps the controller state per retained frame, so a track can be attributed to the player and the sidecar can say which inputs it exercised

- Status: accepted (2026-09-12, by the user) — §1 and §2 implemented the
  same day (the retained frame carries the two port bytes, `poses.json`
  writes the `input` block; PRD §3 record under F9.22). §3 is decided on
  the first kit measurement (`runs/golden-20260912/spike-pose-driver.md`):
  the rule is **interruption**, and it ships as Phase 9 slice **F9.23** in
  `docs/roadmap/PRD-mesence-enhancement-ecosystem.md` once the probe
  scripts §3 requires exist to measure it against.
- Date: 2026-09-12
- Related: ADR-0179 (tracks, `cycles[]` and `sequences[]` — this attributes
  them and depends on its §1 linker; F9.20), F9.22 (per-stage recording —
  the tooling that *improves* coverage, where §2 below only *reports* it),
  ADR-0180 (parts; `proposed`),
  ADR-0170 (the pose sidecar), ADR-0171 (the pose as the unit), ADR-0173
  (the "recorder classifies and labels, consumer filters" rule this follows),
  ADR-0177 (`fusionOf`), ADR-0164 (`adjacency.json`)
- Supersedes / amends: ADR-0170 §1 — `poses.json` gains an optional
  top-level `input` block, and a `cycles[]`/`sequences[]` entry gains an
  optional `driver`. Nothing about how a pose is found, identified, counted,
  ordered or linked changes.

## Context

ADR-0179 derives animation order from the data the recorder already retains:
clusters are linked across consecutive retained frames into tracks, and
cycles are found on a track's pose sequence. It needs no new capture, and the
measurement on Contra produced the artist's own six-column run. **Ordering is
solved, and it is solved without input.**

Two things it cannot answer, and both are named in its own text:

1. **Which track is the player's.** ADR-0179's non-goals list "identifying
   the same character across cycles (a subject)". Contra's spike found the
   enemy soldier's run (two 3-cycles) and the player's somersault (a 4-cycle)
   side by side, distinguished only by a human recognising them. Every
   statistic in the file today is correlational — frame counts, adjacency,
   succession — so there is nothing to break the tie between "this figure
   recurs a lot" and "this figure is the one you control".

2. **What the recording never exercised.** ADR-0179's Consequences already
   state the limitation: *"A cycle is what the recording showed, not what the
   game has. The player's aim-up and aim-down runs are absent from the Contra
   golden sidecar because the entry script never pressed those
   combinations."* The file is silently incomplete, and an artist has no way
   to tell a state the game does not have from a state the run never reached.

The controller is the one **exogenous** signal available in a recording. It
is not a property of the picture that happens to correlate with another
property of the picture: it is the input the emulator was driven with, known
exactly, and the closest thing to a controlled experiment the pipeline has.
`NesConsole` already calls `HdPackBuilder::OnFrameEnd` with the control
manager in scope, and `NesController` already packs its eight buttons into
one byte, so the evidence costs two bytes per retained frame.

Non-goals: naming a state ("run", "jump") — the file records structure, not
semantics, as ADR-0179 §Non-goals has it; inferring intent or difficulty;
anything at run time; any change to clustering, identity, thresholds or the
`hires.txt` key path; replacing ADR-0179's linker, which this depends on
rather than alters.

## Decision

### 1. The retained frame carries the buttons that were held (firm)

`MesenSheets::OamFrame` gains `uint8_t Buttons[2] = {}` — the packed button
byte of ports 1 and 2, in the bit order `NesController` already writes
(A, B, Select, Start, Up, Down, Left, Right), read at frame end.
`HdPackBuilder::OnFrameEnd` takes them as parameters and `NesConsole` passes
them from its control manager; a port with no controller, or a non-controller
device, contributes `0`.

The de-duplication rule of `RecordOamFrame` is **unchanged**: a frame is
still collapsed into `RepeatCount` on `SameEntries` alone. Two frames with
identical sprites and different buttons stay one retained frame, and it keeps
the buttons of the first. This is deliberate — making input part of frame
identity would inflate the retained stream with frames that look the same,
which is the opposite of what the stream is for. The consequence is stated in
§Consequences and is what §3's rule has to tolerate.

This clause is firm regardless of what §3 and §4 settle: capturing the
evidence is cheap, additive, and is the prerequisite for measuring anything
at all.

### 2. The sidecar reports what the recording exercised

`poses.json` gains an optional top-level `input` block, written whenever any
button was ever seen held:

```json
"input": {
  "frames": 3211,
  "ports": 1,
  "held": { "A": 412, "B": 1180, "Up": 96, "Down": 201, "Left": 733, "Right": 1502 },
  "never": ["Select", "Start", "Up+A"]
}
```

`frames` is the retained frames the block is computed over, `held` counts
retained frames (weighted by `RepeatCount`) in which each button was down,
and `never` names the buttons and the directional+action pairs the run never
held at once. `never` is the point of the block: it turns "this sidecar is
incomplete" into "this sidecar says which inputs it exercised", which is what
ADR-0179's consequence asks for and cannot provide. F9.22 attacks the same
consequence from the other side, by recording more; the two are complements,
and `never` is what tells F9.22's tooling whether it worked.

This clause needs no rule and no threshold — it is a report of what happened.

### 3. `driver` — attributing a cycle to a port, by interruption

A `cycles[]` or `sequences[]` entry gains an optional
`"driver": "port1" | "port2"`. What it has to distinguish is "this figure
moves while you hold Right" from "this figure happens to move a lot", and
three candidate shapes were measured on 2026-09-12
(`runs/golden-20260912/spike-pose-driver.md`; the tracks come out of the
recorder under `MESEN_POSE_TRACK_DUMP`, the buttons ride on
`MESEN_OAM_STREAM_DUMP`):

- **Conditional frequency** (the pose's share of retained frames under a
  held button against its share overall) attributes Zelda's four walks to
  the four directions with a 3x margin — and attributes eleven enemy cycles
  to Up for having been on screen while Up was held. Where one button is
  held most of the run it says nothing: Contra's player and soldier runs
  both score Right 1.14, Excitebike's wheels score A 1.00 for player and
  rivals alike, Mega Man 3's runs 1.09–1.14. It is the frequency argument
  ADR-0177 rejected, failing the same way. **Rejected.**
- **Lagged correlation** (phase advances against the button byte over a lag
  window) inherits the same confound and adds a constant. **Rejected.**
- **Interruption** — a cycle that stops within a few frames of the button
  being released — is the only shape that is not a frequency argument, and
  the only one that says what "you control it" means. **This is the rule.**

The rule: over the *windows* of a cycle (maximal stretches of one track
matching the cycle around the loop for >= 2 periods), a port is the
cycle's `driver` when at least `kDriverMinWindows` windows exist, at least
`kDriverStopShare` of their ends follow a release of some button on that
port within `kDriverStopLag` frames, and the other port does not pass the
same test. A cycle that fails any clause gets no `driver`. Excitebike's
wheels are the counter-case the rule must fail on: releasing A does not
stop them, so they never earn a `driver`, rival or player alike.

**Precondition.** Interruption is measurable only where the run releases
buttons. A script that holds Right 87 % of the time (Contra `stage1-run`)
yields one window per cycle per minute and windows that end on fusions,
not releases; nothing can be attributed from it, and nothing should be.
F9.23 therefore ships with a *probe* script per golden game — hold,
release, idle, on a screen with nothing walking into the figure — and the
acceptance measurement is run on those, not on the entry scripts. Contra
is the acceptance case (player's run attributed to port 1, soldier's not),
Excitebike the counter-case (no `driver` written).

What §2 already delivers stands on its own: the Contra stage-1 sidecar says
`never: Select, Start, Left, Up+A, Down+A, Down+B`, naming the aim-while-
jumping and prone-shooting states ADR-0179 could only assert were absent.

### 4. Thresholds

Beside the other pose constants in `TileSheetTypes.h`, to be set by the
F9.23 measurement and moved as a recording change, not a format change.
Starting values, from the spike: `kDriverMinWindows` = 4 (below that a
single fusion decides the share), `kDriverStopLag` = 12 frames (the
longest release-to-stop distance seen on Zelda's walks was under 8),
`kDriverStopShare` = 2/3 (Zelda's Down walk scored 1.00, the confounded
attributions 0.00–0.20).

### 5. Label, do not delete

An unattributed cycle is written exactly as ADR-0179 writes it. `driver` is
present only when the rule fires; its absence means *not classified*, never
*proved not to be the player's* — the ADR-0173 rule, unchanged. No consumer
may drop a cycle for lacking a `driver`; the composition editor may order
attributed cycles first, which is a view decision and F9.18's business.

## Consequences

- **Input is not part of frame identity**, so a held button that changes
  nothing on screen is under-counted: a frame repeated 60 times contributes
  its first frame's buttons. `held` is therefore a lower bound on attention,
  not a duty cycle, and §3's rule must not assume otherwise. Making it exact
  would mean retaining frames that are visually identical, which the stream
  exists to avoid.
- **A recording with no input carries none of this.** A passive capture, a
  demo/attract-mode run, or a run whose script only presses Start writes the
  `input` block (mostly `never`) and no `driver` at all. That is the honest
  outcome, and `never` says so out loud.
- A pack recorded before this ADR reads exactly as it does today: both new
  fields are optional on read, as `fusionOf` and `next[]` are.
- **This makes the entry scripts part of the evidence.** `runs/*/entry.txt`
  currently exists to reach gameplay; once `never` is in the file, a script
  that does not exercise a game's moves produces a sidecar that says so, and
  improving coverage becomes a measurable task rather than a guess. That is
  the measurement F9.22's per-stage recording currently lacks: on the Contra
  golden re-record the player's period-6 run failed to close a cycle because
  the script never held Right for two full turns, and nothing in the file
  said so.
- The file grows by one small block plus one short string per attributed
  cycle.
- It depends on ADR-0179's §1 linker. §1 and §2 shipped on their own
  (2026-09-12) and are useful without §3 — the `never` list needs no
  tracks; §3 is F9.23.
- Two bytes per retained frame on a 4096-frame cap is 8 KB of recorder
  memory, and nothing on disk beyond the block above.
