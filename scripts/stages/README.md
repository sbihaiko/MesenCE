# Per-stage recording scripts (F9.22)

Input scripts for `scripts/headless_record` (`<count>f <buttons>` lines), one
folder per golden game. Two kinds:

- `mint-<stage>.txt` — plays from power-on to the start of a stage. Run with
  `save-state=<stages-dir>/<stage>.mss` to mint the state that stage's
  recording starts from.
- `<stage>.txt` — plays *from* the state for <= 60 s, holding a direction long
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
(30 lives) — load that state in the GUI to reach the later stages and save a
slot at the start of each; those slots are the `.mss` the batch wants.

Measured 2026-09-12 (60 s from each stage-1 state): Contra 2 cycles (the
player's period-6 run on 10-tile poses and the soldier's on 8-tile ones),
Mega Man 3 7 (the run as `001 002 001 003`, period 4 with the middle frame
twice, 34 repeats), Zelda 1 15 (Link's two-frame walk in every direction,
hold 6), Excitebike 8 (the wheels, 398 repeats). Cycles with a period above
6 and a hold near 100 are echoes of the script's own loop, not animations.

A run from a state counts its <seconds> and its script from the state's
frame (`headless_record` prints both); before 2026-09-12 both were absolute
emulator frames, so a state older than the run ended it on the spot.
