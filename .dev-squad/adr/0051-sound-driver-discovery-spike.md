# ADR-0051: Enumerating a game's music and SFX without playing it (sound-driver discovery)

- Status: proposed (spike validated on Mega Man, 2026-08-25; generalisation pending)
- Date: 2026-08-25
- Fase 5, F5.4f. Complements ADR-0047 (fingerprint trigger) and F5.3 (bootstrap recorder).

## Context
F5.3 records music only while the user plays: a track the user never reaches is
never fingerprinted, never gets a MIDI, never gets an OGG. Static extraction is
impossible — the music is engine-specific byte code interpreted by 6502 code in
the ROM — but NSF rippers solve the same problem by *driving the game's own
sound engine*: find the driver, find its "play song N" entry, call it for every N.
The question was whether a headless harness can discover those two things
automatically with the debugger API, with no per-game knowledge.

## Spike (`scripts/spike_sound_driver.cpp`, `make spike-sound-driver`)
Three phases, all generic (nothing Capcom-specific in the code):

A. **Driver tick.** Write breakpoints on `$4000–$4017`; on each break record the
   PC and the callstack. The writers cluster in one code region; the outermost
   callstack frame that lands in that region is the per-frame tick `P` (Mega
   Man: writers at `$9230…`, region `$8A30–$9FFF` in PRG bank 4, `P = $9000`,
   called from the NMI handler `$D4A8` at `$D551`).
B. **Public entry.** Scan the PRG file for `JSR` opcodes whose target lands in
   the driver region but whose site lies outside the driver's own bank; break on
   those sites by **absolute** address (`NesPrgRom`, immune to bank aliasing)
   while a scripted Start press changes the music. A site is accepted only if
   the byte at the PC really is `$20` (exec breakpoints also fire on operand
   fetches — `STA $2007` looked like a JSR). The site hit *after* the press
   whose target is not `P` is the entry `S`; the register whose value varies
   across hits carries the id (ties → A). Mega Man: `S = $9003`, `A = id`,
   called from the NMI's request-queue drain at `$D567` (`$45` = count,
   `$0580+` = ids; `$FC–$FF` are commands, else `ASL; TAX; LDA $9A60,X`).
C. **Enumerate.** For each id: reload the title save state, break at `P` (we are
   inside the NMI with the driver bank mapped), set `PC = S`, `A = id`, push a
   return into a `JMP $0780` stub in RAM, resume. The game logic never runs
   again, NMIs keep ticking the driver, and the APU state is sampled per frame
   with the F5.3 audibility rules → kind (`bgm` ≥ 3 s, `sfx`, `short`), length,
   onset fingerprint.

Result on Mega Man: ids 0–50 are valid (ids ≥ `$33` are rejected by the
game's own queue drain, `CMP #$33`); 51 ids × 4 s → **18 bgm, 22 sfx, 11 very
short (1–5 audible frames), 40 distinct fingerprints** — every stage theme,
boss, Wily, ending, game over, jingles and effects, from a ROM whose title
screen is silent, without a single frame of gameplay. With `SPIKE_BOOTSTRAP=1`
the run happens on a private copy of the ROM with the MEP bootstrap on and a
1.3 s silent gap between ids (the F5.3 segmenter closes a track after 60
silent frames): the recorder wrote `auto/audio/fingerprints.json` with **50
tracks (18 bgm + 32 sfx) and 50 MIDI files** in one 5-minute run.

## Pitfalls found (worth keeping)
- `IsExecutionStopped()` is also true while the emu thread is paused by *our
  own* API calls (`WaitForLock`) → phantom stops. Use the `CodeBreak`
  notification (`RegisterNotificationCallback`) to detect real breaks.
- Wall-clock is meaningless once breakpoints slow the emulation: wait for
  `Ppu.FrameCount`, not seconds.
- Debugger input overrides need a controller on port 1
  (`NesConfig.Port1.Type = NesController`); headless default is none.
- Title screens ignore input during timed waits (`DEC $3C; BNE`) and detect
  presses by edge: pulse Start (3 frames down / 3 up) for a few seconds.
- The trace logger (`[ByteCode] [EffectiveAddress] A X Y F:[FrameCount]`)
  was the fastest way to understand a stuck transition; it also finds RAM
  mailboxes when a game never `JSR`s into its driver.

## Decision (proposed)
Promote the spike to **F5.4f — audio bootstrap without playing**: at first
load of a NES ROM (or from *Open Game Folder → Extract audio*), run phases A–C
headless in the background on a private copy of the ROM and feed the tracks to
the F5.3 recorder. Conditions before accepting: repeat on 3 other drivers
(Konami — Castlevania; Nintendo — Zelda/Excitebike; Sunsoft or Rare) to see
which of these fail: (1) driver in a bank without a fixed-bank trampoline,
(2) request through a RAM mailbox with no `JSR` (fallback: trace-based mailbox
discovery, prototyped and removed from the spike), (3) id in a table index
rather than a register, (4) two entries (music vs SFX). Titles with music
need no Start press: the entry is found from the boot sequence alone.

## Consequences
- `+` Complete `auto/audio` for the whole game at first load; the F5.3 OGG
  replacement then works for every track the player will ever hear.
- `+` No per-game tables, no NSF database; works on ROM hacks.
- `−` Runs the game's own code with a hijacked stack: a few ids will do
  nothing or hang (cap the sampling window; a `JMP`-self stub contains it).
- `−` Enumerated ids are not named; naming stays a human step (or a later
  match against the tracks the player actually reaches).
