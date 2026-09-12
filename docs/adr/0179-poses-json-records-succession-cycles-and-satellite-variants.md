# ADR-0179: `poses.json` records pose succession, the cycles and sequences found on it, and labels a figure-plus-projectile as a variant of the figure

- Status: accepted (2026-09-12, by the user, after the spike below) —
  implemented the same day as Phase 9 slice F9.20 in
  `docs/roadmap/PRD-mesence-enhancement-ecosystem.md` (Part A §3)
- Date: 2026-09-12
- Related: ADR-0170 (the pose sidecar this amends; its non-goals name
  "ordering poses into an animation" as a separate question — this is that
  question), ADR-0171 (the pose as the unit of the sprite layer), ADR-0177
  (`fusionOf`; §Context names the residue this labels), ADR-0173 / ADR-0176
  (the label-don't-delete rule and the "statistic vs. belonging" shape),
  PRD Part A §4 Phase 9 validation test 2, `runs/golden-20260912/spike-pose-succession.md`
  (not versioned)
- Supersedes / amends: ADR-0170 §1 — a `poses[]` entry gains optional
  `next[]` and `variantOf`; the file gains optional top-level `cycles[]` and
  `sequences[]`. Nothing about how a pose is found, identified, counted or
  ordered changes.

## Context

The Phase 9 side-by-side (validation test 2) put our Contra pose sidecar
next to the artist's `BillRizer.png`. The artist's unit is a whole figure per
animation phase, laid out as a grid: one row per state, one column per
phase, six run columns. Our sidecar carries the same figures — 64 poses after
ADR-0177 — as an unordered list sorted by frame count. An artist opening it
meets the player's run as five entries scattered among explosions and enemy
frames, with nothing saying they belong to one loop or in what order.

ADR-0170 deliberately left this out ("not an animation format ... ordering
poses into an animation ... are separate questions"). The spike run on
2026-09-12 (`runs/golden-20260912/spike-pose-succession.md`) measured whether
the order is derivable from the data the recorder already retains, without
any change to capture. It is, with one twist:

- The retained `_oamFrames` stream is ordered and `RepeatCount`-collapsed.
  Linking each kept cluster in frame *i* to the nearest kept cluster in frame
  *i+1* (top-left within 16 px Manhattan) yields tracks. On Contra the enemy
  soldier's run comes out as two closed 3-cycles with weakest edge >= 14
  (`pose000 -> pose011 -> pose010` and `pose000 -> pose016 -> pose008`), the
  player's somersault as a 4-cycle (`pose006 -> pose015 -> pose017 -> pose013`,
  weakest edge 7).
- **A first-order graph is not enough.** The player's run is a 6-phase
  cycle held 8 frames per phase — `020 003 022 023 003 024` — in which
  `pose003` is *both* phase 2 and phase 5, because a silhouette identity
  cannot tell two phases whose tiles coincide. On the successor graph that
  reads as a 3-cycle with a fork; on the track it reads as period 6, exactly
  the artist's six columns. Cycles therefore have to be found on the sequence
  of a track, not on `next[]`.
- Linear, non-looping animations recur too: the player's death is the run
  `068 033 042 046 050 049 048 034 047`, seen twice, identically.
- The flicker hypothesis for the low-frame poses was wrong (the suspected
  blue "legs" are explosions), so there is no `partialOf` to define. What the
  data does hold is the residue ADR-0177 §Context already named: 9 of 64
  kept poses are another kept pose plus 1–3 tiles — a soldier plus his muzzle
  flash (`pose025 = pose001 + shot`). Containment alone decides it.

Non-goals: naming an animation ("run", "jump", "death") — the file records
structure, not semantics; identifying the same character across cycles (a
subject) — ADR-0180 territory; any change to the clustering, the identity or
the thresholds of ADR-0170; any change to capture, to `kMaxSheetFrames` or
to `hires.txt`; anything at run time.

## Decision

### 1. Tracks are linked at save time, from the retained stream

For every pair of consecutive retained frames, each kept cluster in the
earlier frame is linked to the kept cluster in the later frame whose top-left
is nearest, within `kPoseTrackMaxMove` = 16 px Manhattan, each later cluster
used at most once, nearest first. A cluster with no partner ends its track.
This is a free function next to `BuildPoses` in
`Core/NES/HdPacks/SpriteGrouping.{h,cpp}`, host-free (ADR-0127), returning
tracks as sequences of `(pose index, held frames)` where `held` sums
`RepeatCount` over the frames the pose was held. Frames are walked in stream
order; a pose below the ADR-0170 §2 thresholds is invisible to the linker,
never a track member.

### 2. `next[]` — first-order succession, per pose

Every kept entry gains an optional `next[]`: the poses this one was linked
to, with the count of links, most-linked first, self-links excluded and
reported as `hold`. Written only when non-empty.

```json
{ "id": "pose003", "frames": 644, "hold": 605, "size": [3, 6],
  "next": [ {"pose": "pose022", "count": 6}, {"pose": "pose024", "count": 5} ],
  "tiles": [ … ] }
```

`next[]` is the raw evidence; it is what a reader needs to check §3 and it
does not pretend to be the animation (see the fork at `pose003`).

### 3. `cycles[]` and `sequences[]` — found on tracks, by repetition

Top-level, optional, written only when non-empty:

- A **cycle** is a run of poses of period *p* >= 2 that repeats at least
  `kPoseCycleMinRepeats` = 2 consecutive times on one track, with at least 2
  distinct poses. Period detection is on the track's pose sequence (holds
  ignored for matching, reported after); the shortest period that repeats
  wins, and the phase is rotated so the most-seen pose is first. Equal cycles
  from different tracks merge, summing `repeats`.
- A **sequence** is a run of >= `kPoseSequenceMinLength` = 3 distinct poses,
  not part of any cycle, that occurs identically on at least 2 tracks (or
  twice on one). It is the non-looping animation: a death, a spawn, an
  explosion.

```json
"cycles": [
  { "id": "cycle000", "period": 6, "repeats": 11,
    "poses": ["pose003", "pose022", "pose023", "pose003", "pose024", "pose020"],
    "hold":  [8, 8, 8, 8, 8, 8] },
  { "id": "cycle001", "period": 3, "repeats": 20,
    "poses": ["pose000", "pose011", "pose010"], "hold": [8, 8, 8] }
],
"sequences": [
  { "id": "seq000", "repeats": 2,
    "poses": ["pose068", "pose033", "pose042", "pose046", "pose050", "pose049", "pose048", "pose034", "pose047"],
    "hold":  [2, 4, 4, 4, 4, 4, 4, 2, 2] }
]
```

A pose may appear in several cycles and in a cycle more than once (that is
the whole point of §Context's twist). `hold` is the median held frames per
phase over the repeats, so a reader can play the loop at the game's own
cadence without `frameRange`. Ordering: cycles by `repeats` descending then
by `poses`; sequences the same. The ids are positions in that order, as
ADR-0170 §1 does for poses.

### 4. `variantOf` — a kept pose that is another kept pose plus a satellite

A kept, non-fusion pose `V` is a **variant** of kept pose `P` when some
translation of `P`'s tiles is a strict subset of `V`'s and the remainder has
fewer than `kPoseMinTiles` tiles (so the remainder could never be a pose —
otherwise ADR-0177's fusion rule applies and wins). Candidates `P` are tried
in file order and the first match is named. Written as an id, like
`fusionOf`:

```json
{ "id": "pose025", "frames": 31, "size": [3, 6], "variantOf": "pose001", "tiles": [ … ] }
```

Containment only, no threshold, no temporal evidence: the spike found the
same 9 of 64 by containment and by adjacency. A consumer that chooses a
figure (`compose_engine.pose_band_members`, `pose_for_anchor`) ranks the
base pose above its variants, and a variant stays reachable by id — the
ADR-0173/0177 rule, unchanged. `PosesForCells` keeps citing variants: the
projectile's tiles belong to the sheet, and the variant is the only pose that
holds them.

### 5. The consumer lays poses out by cycle

The composition editor's pose picker and any future subject sheet order the
sprite side as the artist does: one row per cycle or sequence, columns in
phase order, the unordered remainder after. This is the only consumer change
this ADR asks for; the layout itself is F9.18's business.

### 6. Tests

`core_unit_tests` (ADR-0126) with hand-built streams: a track follows a
figure moving 3 px per frame and breaks at 17 px; a 6-phase cycle with a
repeated silhouette is reported with period 6, not 3; two identical
non-looping runs become one sequence with `repeats: 2`; a pose plus a
1-tile satellite is a variant, a pose plus a 4-tile remainder that is itself
a pose is a fusion and not a variant; a pack whose stream has no repetition
writes no `cycles`/`sequences` key at all.

## Consequences

- The file grows by the succession data only where there is any; a pack
  recorded before this ADR reads exactly as it does today (every new field
  is optional on read, as ADR-0177's `fusionOf` is).
- **A cycle is what the recording showed, not what the game has.** The
  player's aim-up and aim-down runs are absent from the Contra golden
  sidecar because the entry script never pressed those combinations, and
  no amount of sidecar work invents them; that is the per-stage recording
  roadmap's job (PRD Phase 9, F9.22). Likewise a cycle observed once
  (`repeats: 1`) is not written, so a rare animation stays an unordered
  pose. The recorder reports found/kept counts for cycles and sequences on
  the save line, as ADR-0170 §2 does for poses.
- **The 4096-frame cap now costs order, not just coverage.** On the 120 s
  Contra run the stream held 4151 of 7213 frames, so the last 51 s produced
  no poses and no tracks. This ADR leaves `kMaxSheetFrames` alone (it bounds
  memory at ~11.5 MB, ADR-0170's own reason) and pushes the answer to the
  recording shape: several ~60 s runs from per-stage save states, not one
  long run. Raising the cap is a separate decision if that proves
  insufficient.
- Track linking is greedy nearest-first, so two identical figures crossing
  paths can swap tracks for a frame. That produces a spurious edge, never a
  spurious cycle: a cycle needs `repeats >= 2` of the same period on one
  track. Fusions (ADR-0177) are kept poses and do take part in tracks, so a
  cycle can pass through a fusion; the consumer's fusion filter applies
  after, as it does today.
- `hold` is a median in retained frames, i.e. after `RepeatCount` collapse
  summed back — the game's cadence, as long as the emulator ran at full
  speed. A paused screen inflates one phase's hold, not the cycle.
- Nothing here names anything. "cycle000" is the player's run only because a
  human recognises it; the file says period 6, repeats 11.
- **What the Contra golden run actually wrote** (2026-09-12, at delivery):
  5 cycles, 8 sequences, 690 tracks. The soldier's two 3-cycles of §Context
  merge into one period-6 cycle (`000 011 010 000 016 008`, 5 repeats) —
  the soldier alternates between them, so the shortest repeating period is
  6, and the rule reports that. The player's run is *not* a cycle: no track
  holds it for two full turns (the longest is 8 phases), because the entry
  script taps R in bursts. It shows up as four 3–4-pose sequences instead.
  A sequence that is a window of a cycle (a soldier who walked one and a
  half turns and died) is folded into the cycle, matched around the loop, as
  §3's "not part of any cycle" asks. A base pose alternating with its
  variant (`pose001` ↔ `pose025`, the muzzle flash) is a period-2 cycle by
  the letter of §3 and is written as one.
