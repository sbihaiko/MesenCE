# ADR-0135: Sound-driver probe runtime contract: opt-in, time budget, abort, no-op

- Status: proposed (productisation contract for F5.4f / F5 closeout item 11; nothing beyond the spike exists in the tree)
- Date: 2026-08-29 (restored from b0b334b0^; originally dated 2026-08-27)
- Consolidates: ADR-0093, ADR-0096, ADR-0099
- Related: ADR-0051 (sound-driver discovery spike — this ADR supplies the runtime contract 0051 lacks), ADR-0043 (shortcut wiring precedent), ADR-0047, ADR-0052

## Context

ADR-0051 recorded the spike (`scripts/spike_sound_driver.cpp`, `make
spike-sound-driver`, `makefile:254`): drive the game's own sound driver via
debugger breakpoints and JSR/mailbox discovery to enumerate every music and
SFX id without gameplay. On 12 ROMs it produced a validated trigger on 5–6
(Mega Man, Castlevania, Zelda, Punch-Out!!, SMB3, Ninja Gaiden plausible) and
nothing on the rest (Bomberman corrupted state; 1943, Contra, Excitebike,
Gauntlet, SMB1 found the tick but validated no trigger). Its proposed Decision
already says: ship as an **opt-in tool** behind *Open Game Folder → Extract
audio*, writing into the sibling folder's `auto/audio/` through the F5.3
recorder, with the enumeration log kept beside it.

The F5 closeout spec (run `d662e62e2648`) planned to promote this into an
in-process, shortcut-triggered feature (`EmulatorShortcut::ExtractAudioHdPack`,
a `NesSoundDriverProbe` class, an `OpenGameFolder` entry in
`UI/ViewModels/HdPackBuilderViewModel.cs`). None of it exists: `grep
ExtractAudioHdPack Core UI` returns nothing; the only comparable shortcut is
`ExportRomTilesHdPack`. ADR-0096 and ADR-0099 point out that promoting a
technique with a ~50 % failure mode into a live feature that runs the game's
code with a hijacked stack, inside the emulator process, needs a *failure
contract* that 0051 does not state: how the user opts in, how long it may run,
how it is stopped, what happens on an unsupported ROM, and on which thread it
runs. ADR-0093 adds that the spec's acceptance criteria only checked the C++
enum entry, while the precedent touches ~8 files.

## Decision

Proposed runtime contract for the productised probe:

1. **Opt-in only.** Never runs at ROM load or on any automatic path. Entry
   points: a menu action under *Open Game Folder → Extract audio…* and an
   `EmulatorShortcut::ExtractAudioHdPack` (unbound by default). The UI text
   states up front that the probe "may find nothing" on this ROM and lists
   what it will write (`auto/audio/fingerprints.json`, `midi/`, an
   enumeration log).
2. **Hard budget.** Two independent caps, both from settings with fixed
   defaults derived from the spike (24 ids × 3 s per phase, ~5 min total on
   Mega Man): a wall-clock budget for the whole run and a per-id frame budget
   (`Ppu.FrameCount`-based, not seconds — breakpoints make wall-clock
   meaningless, ADR-0051 pitfalls). An id that exceeds its frame budget or
   traps into a `JMP`-self stub is recorded as "no result" and the run moves
   on; the whole run stops at the wall-clock cap with a partial result.
3. **Abortable.** The run is cancellable from the UI at any time; abort is
   honoured at the next frame boundary. Abort or budget exhaustion always
   restores the pre-run state (see 5) and keeps whatever was already written.
4. **Guaranteed no-op on unsupported ROMs.** Phase A/B validation (≥ 3 ids give
   distinct results, same id reproduces the same novel onsets on two save
   states) is mandatory; if no trigger validates, the probe writes nothing to
   `auto/audio/` except the enumeration log stating "no validated trigger", and
   the emulator state is exactly as before. No partial fingerprints from an
   unvalidated candidate (the Bomberman corruption case).
5. **Isolation.** The probe runs on a private copy of the console state: it
   saves a state before starting, runs on the emulation thread under the
   debugger (it needs breakpoints, the `CodeBreak` notification and
   `NesPrgRom` absolute breakpoints), and restores the saved state and the
   user's controller/debugger configuration when it ends for any reason.
   `SPIKE_BOOTSTRAP=1`'s "private copy of the ROM" becomes "private state
   snapshot" in-process. Running on a snapshot in a second `Emulator` instance
   is the alternative if the debugger cannot be attached without disturbing the
   user's session (see Alternatives).
6. **Output.** Same files as the F5.3 recorder (`auto/audio/fingerprints.json`
   + MIDI per track) plus `auto/audio/enumeration.log` with the tick, trigger,
   per-id verdicts and rejected candidates, so a human can prune garbage ids.
7. **Shortcut-wiring checklist (from ADR-0093, precedent `ExportRomTilesHdPack`).**
   The feature is complete only when all of these reference the new shortcut,
   and the acceptance criteria verify each:
   - `Core/Shared/SettingTypes.h` (`EmulatorShortcut` enum, cf. `:1143`)
   - `UI/Config/Shortcuts/EmulatorShortcut.cs` (C# mirror enum, cf. `:143`)
   - `Core/NES/NesConsole.{h,cpp}` shortcut switch and handler (cf. `.cpp:916,
     :923`) — NES only for the probe; GB/SMS switches
     (`Core/Gameboy/Gameboy.cpp:776`, `Core/SMS/SmsConsole.cpp:386`) must
     reject or ignore it explicitly
   - `Core/Shared/EnhancementPacks/MepPackManager.cpp` (cf. `:307`) if the
     pack manager dispatches it
   - `UI/ViewModels/HdPackBuilderViewModel.cs` (cf. `:128`) or the Open Game
     Folder view model that exposes the action
   - localisation resources for the new menu/dialog strings.

## Consequences

- The ~50 % miss rate becomes an explicit, bounded, user-initiated outcome
  ("no validated trigger") rather than a hang, a corrupted session or silent
  garbage in `auto/audio/`.
- Budget and abort make the worst case predictable (minutes, not open-ended);
  the state snapshot makes the best case indistinguishable from never having
  run it.
- Cost: debugger attach/detach and save-state churn inside the emulator
  process; NES-only until GB/SMS drivers are studied.
- This ADR moves to `accepted` when the feature ships with all seven points
  verifiable; ADR-0051 stays the record of the technique and its measured hit
  rate.

## Alternatives

- **Automatic at ROM load** — rejected (ADR-0051 already): hit rate and
  duration are unacceptable as a silent step.
- **Keep it a headless script only** (`scripts/spike_sound_driver …
  SPIKE_BOOTSTRAP=1`) — viable interim; loses the "first load fills
  `auto/audio`" promise for GUI users but carries no in-process risk.
- **Run on a snapshot in a separate `Emulator` instance** instead of the live
  emulation thread — cleaner isolation, but doubles memory and needs the
  debugger API on a second instance; choose during implementation if in-place
  save/restore proves fragile.
- **Only verify the enum entry in acceptance criteria** (the original spec) —
  rejected per ADR-0093; an enum value without the switch cases and the C#
  mirror is not a feature.
