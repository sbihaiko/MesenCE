# ADR-0162: An accuracy suite is run against our own binary in several configurations, and the frames must be identical

- Status: proposed — implemented as `scripts/accuracy_compare.py` + `scripts/test_accuracy_compare.py`, listed as slice **H10** in `docs/roadmap/PRD-mesence-enhancement-ecosystem.md` §4 "Repo hygiene and tests". Only a human marks this accepted.
- Date: 2026-09-05
- Related: ADR-0157 (headless input counted in emulated frames), ADR-0159 (in-memory frame capture, `Core/Shared/Video/FrameCapture.h`), ADR-0005 (MEP textures as an envelope over HD Pack), ADR-0050 (bootstrap builder), ADR-0133 (NES mixer replacement), ADR-0137 (`make doc-checks`), ADR-0131 (`unit-tests.yml` builds no core), PRD Part A slice H10
- Prior art: `100thCoin/AccuracyCoin` (MIT, Chris Siebert) — the test ROM; `Core/Shared/RecordedRomTest.{h,cpp}` — upstream's own deterministic replay harness, which is where the "zero power-on RAM or the comparison is noise" lesson came from

## Context

This fork's whole product is a set of optional layers bolted onto an accurate
emulator:

- the **HD Pack Builder** runs inside the PPU while a game plays, recording
  tiles, OAM snapshots and whole screens (ADR-0050, ADR-0153, ADR-0156);
- **MEP** replaces textures and audio at load time and during rendering
  (ADR-0005, ADR-0138);
- the **Enhanced Synth** taps the APU and can mute and replace channels
  (ADR-0133).

Every one of them is a hook into a hot path of an emulator whose reason to
exist is that it is accurate. The risk that actually matters to a user is not
"is Mesen accurate" — that is upstream's problem and upstream's achievement —
but **"does the game behave differently because one of our layers is on"**. A
tile-recording hook that perturbs PPU timing, a texture lookup that changes
what a mid-frame read returns, a mixer replacement that shifts DMC timing:
each would show up as a game that plays subtly wrong only in our build, only
with a pack installed. Nothing in this repo tested for that. `mep_compare.py`
compares *pictures*, `smoke_pack_headless.sh` checks that a pack loads, and
the F9 harnesses measure what the builder wrote — none of them asks whether
the machine underneath still computed the same thing.

`100thCoin/AccuracyCoin` is the obvious instrument. It is a single NROM
cartridge carrying 144 NES accuracy tests plus 5 informational "DRAW" screens,
written for an NTSC RP2A03G/RP2C02G console. Start runs the whole suite
unattended and draws a results table — a 22-page grid of per-test success
codes with `TESTS PASSED: n / 144` underneath. Verdicts are **on screen**;
there is no serial log and no documented result address, and this tree exports
no general memory-read entry point (`InteropDLL/DebugApiWrapper.cpp` exposes
`GetConsoleState`, not RAM). So the screen is the result surface, which is
convenient rather than limiting: one 256x240 frame carries all 144 outcomes.

## Decision

**Run an accuracy suite against one binary in several configurations — arms —
and require the captured frames to be byte-identical across them.**

`scripts/accuracy_compare.py` implements it.

### 1. The comparison primitive is the frame checksum ADR-0159 already gives us

Each arm is run by `scripts/headless_record` with the `capture` flag, which
pulls the final frame into memory and prints its dimensions, frame number and
FNV-1a checksum (`Core/Shared/Video/FrameCapture.h`, F9.15). The harness
compares those checksums. No new capture path, no PNG on disk, no image
library.

A checksum is only a fair summary because the suite prints its verdict: the
results table *is* the 144 pass/fail cells. A divergence of one test flips
pixels, and the checksum notices.

The comparison also requires the reported **frame number** to match. Equal
checksums from runs that stopped at different frames prove nothing, and the
harness treats that as a divergence rather than a pass. (This is not
theoretical: an early perturbation experiment forced PAL on one arm, which
changes the frame rate the `<seconds>` argument is resolved at, so the arm
covered frame 150 where the baseline covered 180. The harness refused the run
instead of comparing them.)

### 2. Determinism comes from ADR-0157, not from a new mechanism

A self-comparison is worthless if the two sides are noisy. ADR-0157 already
made a headless run reproducible: input is counted in emulated frames and
resolved from inside the frame, power-on RAM is zeroed, and the run ends when
the core's own counter reaches an absolute frame. The harness inherits all
three and adds nothing. Checkpoints are therefore absolute frame numbers.

Two are used, read off real runs rather than guessed:

| checkpoint | frame | what is on screen |
|---|---|---|
| `boot-menu` | 180 | the menu (`CPU BEHAVIOR`, page 1/22) — art, no test has run |
| `results-table` | 4808 | `TESTS PASSED: 141 / 144`; the table is first drawn at 4207 and static after, so 4808 sits inside the settled window rather than on its edge |

### 3. The arms are our layers, and the art-replacing ones use an *identity pack*

| arm | layer under test |
|---|---|
| `vanilla` | none — the baseline |
| `builder` | the HD Pack Builder recording throughout the run (`hdpack`) |
| `hdpack` | a loose HD pack installed in `HdPacks/<rom>/`, every tile replaced |
| `mep` | a MEP container in `EnhancementPacks/`, textures **and** synth active |

The last two rest on one idea that makes the whole thing work. A texture pack
normally changes the picture on purpose, so "the frames must be identical" is
not a property a texture arm can have. Unless the replacement art *is* the
original art: the harness first records an HD pack with the builder at scale 1
over the whole compared range, then installs **that** pack. The core logs a
100 % background tile match rate — 659 tiles replaced — and the correct output
is still bit-identical to vanilla. The replacement path is fully exercised and
the assertion stays exact.

The alternative — running the texture arm with textures disabled — would test
pack discovery and nothing else.

The `mep` arm is built from the same identity pack by `gen_mep_test_pack.py`,
so it additionally exercises No-Intro SHA-1 matching, container discovery, and
the ESP synth overrides, which is the audio layer's load-time half.

### 4. What a failure means

An arm that diverges from `vanilla` means **one of our layers changed what the
emulator computed** (or what it displayed). It is a defect in this fork, in the
arm's layer, and the checkpoint tells you whether it appears before any test
has run (an art or display fault) or only in the results (a behaviour fault).
It is never a statement about upstream.

### 5. The suite ROM is not vendored

AccuracyCoin is MIT-licensed ("Copyright (c) 2025 Chris Siebert"), so
committing `AccuracyCoin.nes` would be lawful. We still do not:

- the harness should work against any suite a developer holds locally, so a
  path is the honest interface either way;
- a 40 KB binary in the tree acquires a maintenance story (which build? who
  bumps it?) that a documented URL does not;
- `docs/AGENTS.md` keeps derivative game content out of the tree, and a
  vendored ROM would be the first exception argued case by case.

Resolution order is `--rom`, then `$MESENCE_ACCURACY_ROM`, then
`tests/accuracy/AccuracyCoin.nes`. With none of them present the harness
prints `SKIP` and exits **0**; `--require-rom` turns that into exit 2 for a
caller that has provisioned one and wants to know if it went missing. The
harness also warns when the ROM's SHA-1 is not the one the checkpoints were
read from, because the frame numbers would then point at other screens.

### 6. CI: not yet, and the skip path is why

This does **not** join `make doc-checks` or any workflow now.

`doc-checks` is stdlib-only and core-free by construction (ADR-0137);
`unit-tests.yml` deliberately builds no core (ADR-0131); and `build.yml`'s jobs
build the core but have no ROM and no `capture-tool` step. Wiring it in means
provisioning a ROM into CI and adding ~1 minute of emulator runtime per job —
a decision with a cost, which is exactly the sort of thing that should be
decided rather than smuggled in with a harness.

What is settled now is that the harness is **ready** for it: the `SKIP`-and-0
contract means a workflow can call it today and stay green until a ROM is
provisioned, and `--require-rom` is the switch that makes it enforcing. The
pure half is covered by `scripts/test_accuracy_compare.py`, which is stdlib
only and could join a workflow immediately.

Until then it is a local gate: run it before touching the builder, the MEP
texture path or the mixer.

## What this deliberately does not test

- **Upstream's accuracy.** AccuracyCoin reports 141/144 on this tree. Whether
  those three should pass is upstream's business; the harness never asserts on
  the number, only that it is the *same* number in every arm. A suite
  regression that is equally wrong in all four arms passes here, by design.
- **Anything the frame does not show.** Audio is not compared — the synth is
  only covered to the extent that loading and configuring it must not disturb
  video. Comparing rendered audio is a separate slice and would need a
  different primitive.
- **A pack that changes the picture on purpose.** By construction the art arms
  carry identity art. A real community pack's output is *supposed* to differ,
  and comparing it against vanilla pixels would be meaningless.
- **Non-NES consoles.** AccuracyCoin is NES. GB/SMS would need their own suite
  and their own checkpoints; the profile constants are in one block so that is
  additive.
- **Intermediate frames.** Only the declared checkpoints are compared. A
  divergence that appears and heals between two of them is invisible. The
  results table mitigates this for the suite specifically, since it is a
  summary of everything that happened before it.

## Consequences

- A comparison harness that has never failed is not known to work, so the
  ability to go red is part of the deliverable, not an afterthought:
  `--perturb-flag ARM=FLAG` adds a recorder flag to one arm and
  `--perturb-texture ARM` rotates the art of every `<tile>` rule in that arm's
  installed pack by one.
- `--perturb-texture` rotates *all* rules rather than swapping a chosen pair,
  and that is a lesson rather than a preference. The first implementation
  swapped the first two distinct rules; the two tiles it picked are never drawn
  at either checkpoint, so the harness stayed **green on a pack that had in
  fact been tampered with**. Which tiles are on screen at a checkpoint is not
  knowable from the manifest, so the perturbation must touch all of them. The
  helper refuses a rotation that cannot change a pixel (fewer than two rules,
  or every rule pointing at one picture) for the same reason.
- Deleting rules would not work as a perturbation at all: the identity pack's
  art is a copy of the PPU's own output, so a tile that falls back to the PPU
  produces the same pixel.
- Cost: four arms x two checkpoints plus one pack-recording run — nine
  emulator runs, ~46 s wall clock on macOS/arm64. `--arms` narrows it.
- The pure helpers (`parse_capture`, `frames_to_seconds`, `compare`,
  `rotate_tile_art`, `resolve_rom`, `format_report`) are separated from the
  subprocess half per ADR-0127 and covered by `scripts/test_accuracy_compare.py`
  — 38 stdlib-only checks, no ROM, no emulator, no network.
- One negative result worth keeping: an injected fault that made the `builder`
  arm power on with `RamState::AllOnes` did **not** change either checkpoint.
  AccuracyCoin initialises its own RAM, so it is insensitive to power-on state.
  That is a limit of the instrument, not of the harness — a suite is only a
  detector for the behaviours it exercises.

## Alternatives considered

- **Compare RAM instead of pixels.** The natural primitive for "did emulation
  change", and AccuracyCoin's debug menu shows results at `$20-$2F`,
  `$50-$6F` and `$500-$5FF`. Rejected for now because this tree exports no
  memory-read entry point to a headless caller; adding one is a real change to
  `InteropDLL` for a benefit the on-screen results table already delivers. If
  a future suite reports only to memory, this is the slice to reopen.
- **Compare against a vanilla upstream build.** Two binaries, two build
  configurations, and any divergence is ambiguous between "our layer" and "our
  merge". Self-comparison isolates the variable that matters, at the cost of
  saying nothing about upstream parity — which we did not want to say.
- **Assert `TESTS PASSED: 141 / 144` by reading the screen.** Would need
  OCR or a glyph table, and would test upstream's accuracy, which is not the
  question. The checksum covers the same pixels and more.
- **Vendor the ROM and wire it into `build.yml` now.** See §5 and §6; both are
  cheap to revisit and neither is cheap to undo.
