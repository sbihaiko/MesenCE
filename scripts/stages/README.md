# Per-stage recording scripts (F9.22)

Input scripts for `scripts/headless_record` (`<count>f <buttons>` lines), one
folder per golden game. Two kinds:

- `mint-<stage>.txt` — plays from power-on to the start of a stage. Run with
  `save-state=<stages-dir>/<stage>.mss` to mint the state that stage's
  recording starts from.
- `<stage>.txt` — plays *from* the state for <= 60 s (<= 3600 frames, the
  batch's default duration; a longer script is cut where the run ends), holding a direction long
  enough for every loop to complete two turns on one track (ADR-0179 §3 needs
  `repeats >= 2`; a Contra turn is 6 x 8 frames, so `90f R` is 1.9 turns and
  `240f R` is 5).

Mint, then batch:

```sh
scripts/headless_record <rom> <seconds> <work>/mint input=scripts/stages/contra/mint-stage1.txt save-state=<work>/stages/stage1-run.mss
cp scripts/stages/contra/stage1-run.txt <work>/stages/
scripts/record_stages.sh <rom> <work>/stages <work>/by-stage 60
```

The `.mss` files are not versioned: a CHR RAM state carries the game's
graphics. `mint-stage1-30lives.txt` types the Konami code at the Contra title
(30 lives); the later stages are reached headlessly from it.

## Reaching a later stage without a human

A stage is played as a chain of short `headless_record` runs, each loading the
previous `.mss` and saving the next, steered by RAM read off the state with
`scripts/mss_ram.py <file.mss> [addr...]`. For Contra: lives `$0032`, screen
index `$0064`, stage `$0030` (0 = stage 1), player X/Y `$0334`/`$031A`, player
state `$0090` (1 alive, 2 dying), the stage-1 core's HP `$0585` (32, one per
hit); the fine scroll is `((ppu.tmpVideoRamAddr & 0x1f) << 3) | ppu.xScroll`.
Two search shapes were enough on 2026-09-12: a greedy explorer over ~20
candidate windows per hop (`Nf RB` then a jump then `RB`), keeping the window
with the largest `screen * 256 + scroll` that lost no life, crossed stage 1;
a depth-first search over 60 f windows (prone burst, standing burst, jump,
aim up, step left/right, wait) with survival as the constraint and the core's
HP as the objective beat the wall in four prone windows. What the search
found and a human would not guess: from the small platform in front of the
core only prone shots are at its height — standing shots pass above it from
the platform and below it from the ground. The chain and every intermediate
state live under `runs/golden-20260912/contra/play/` (unversioned); the
minted states are `stages/stage1-boss.mss` (the wall, with Bill respawning on
the top-left platform) and `stages/stage2-base.mss` (the corridor, Bill
spawning). A save-state boundary is not input-neutral: the same 600 f prone
script run in one piece and in ten 60 f pieces diverged after ~100 f, so a
chain is reproducible only as a chain, not as one concatenated script.

Measured 2026-09-12 (60 s from each stage-1 state): Contra 2 cycles (the
player's period-6 run on 10-tile poses and the soldier's on 8-tile ones),
Mega Man 3 7 (the run as `001 002 001 003`, period 4 with the middle frame
twice, 34 repeats), Zelda 1 15 (Link's two-frame walk in every direction,
hold 6), Excitebike 8 (the wheels, 398 repeats). Cycles with a period above
6 and a hold near 100 are echoes of the script's own loop, not animations.
From the two later Contra states the same day: `stage1-boss` 69 poses, 3
cycles (all period 2, a pose alternating with its muzzle-flash variant);
`stage2-base` 163 poses, 10 cycles — the base soldier's run as three period-3
cycles of 8-tile poses with hold 4, plus a period-4 cycle of 6–8-tile poses.

Since ADR-0181 §1–§2 (2026-09-12) `poses.json` carries an `input` block:
`held` frames per button and `never`, the buttons and direction+action pairs
the run never held at once. That is the check on a `<stage>.txt`: Contra's
`stage1-run` says `never: Select, Start, Left, Up+A, Down+A, Down+B`, so its
sidecar cannot hold the aim-while-jumping or prone-shooting states, and a
script that wants them has to press them. Two env-gated save-time dumps back
a measurement: `MESEN_OAM_STREAM_DUMP` (retained frame, repeat, port 1 and 2
button bytes, then `node,x,y` per sprite) and `MESEN_POSE_TRACK_DUMP` (one
ADR-0179 track per line as `frame:pose:held`).

A run from a state counts its <seconds> and its script from the state's
frame (`headless_record` prints both); before 2026-09-12 both were absolute
emulator frames, so a state older than the run ended it on the spot.
