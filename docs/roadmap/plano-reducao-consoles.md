# Plan — fork product: `main` + reduced consoles

**Status:** done (2026-08-26) — `main` is the default; NES, GB/GBC/GBS, SMS/GG/SG-1000, and GBA remain. SNES (incl. SGB), PC Engine, WonderSwan, and ColecoVision are out. ·
**PRD:** [PRD-ecossistema-enhancement-comunitario.md](PRD-ecossistema-enhancement-comunitario.md) (SNES was already out of the phases) ·
**Out of spec:** cutting emulation, not the pack format.

This fork has no PR flow to [nesdev-org/MesenCE](https://github.com/nesdev-org/MesenCE) (`CONTRIBUTING.md`). After cutting SNES / PC Engine / WonderSwan / ColecoVision, a `git merge upstream/master` (or GitHub's **Sync fork** button) reintroduces the consoles. That's why switching the main branch comes **before** deleting code.

## Success criterion

The default for `sbihaiko/MesenCE` is `main`. On it, the emulator only loads:

- NES (iNES / UNIF / FDS / NSF / VS)
- Game Boy / GBC / GBS (handheld; **without** Super Game Boy)
- Master System / Game Gear / SG-1000
- GBA

ColecoVision, SNES (emulation: SGB, MSU-1, coprocessors), PC Engine (incl. CD), and WonderSwan don't load ROMs, don't appear in the file dialog, and don't have a system settings screen. CI (clang-format, unit tests, Run tests, Build) green on `main`. Badges and nightly.link point to `main`.

**SNES input stays.** Pad, mouse, and NTT Data Keypad (`ControllerType::SnesController` and related) remain as port devices on the surviving consoles — on NES the dropdown already lists them; a USB/Bluetooth pad with an SNES layout maps on the host like any other pad. Not bringing back the core, Super Scope, Multitap, rumble/BlueRetro (which depended on `SnesConsole`), or `.sfc`/`.spc`.

## Branch decision — yes, change the default

| Branch | Role |
|---|---|
| **`main`** | GitHub default. Product. All new work. Core cuts happen here. |
| **`master`** | Frozen at the last *full-console* snapshot (current state). History + comparison point. No new commits. |
| **`upstream`** (optional, origin) | Fast-forward **only** from `nesdev-org/MesenCE/master`. Never merge wholesale into `main`. Cherry-pick bugfixes, file by file. |

Don't call the product `master`: the habit of `merge upstream/master` and GitHub's **Sync fork** (syncs the fork's default with the parent's default) put SNES/PCE/WS back into the tree.

Name `main` (not `community`): it's the default that GitHub, `nightly.link`, and `actions/checkout` expect; the README already explains that this is the enhancement fork.

**Don't defork now.** The parent stays visible. Document in `CONTRIBUTING.md`: never use Sync fork. Deforking (leaving the fork network) remains a follow-up if Sync fork ever becomes a real accident.

### Steps (F0) — branch, without deleting core

1. From the current `master`: `git branch main && git push -u origin main`.
2. GitHub: default branch → `main` (`gh repo edit sbihaiko/MesenCE --default-branch main`).
3. CI: `clang-format-check.yml` currently triggers only on `push` to `master` — switch it to `main`. The other workflows are already `on: [push, pull_request]`.
4. README: badges `branch%3Amaster` and URLs `nightly.link/.../master/` → `main`.
5. Protect `master` against push (GitHub settings) or simply stop committing to it.
6. Open feature branches (`feature/enhanced-audio-*`, `feature/hdpack-*`, etc.): historical; new work branches off `main`.

## What stays / what goes

The host stays (`Core/Shared/`, debugger shell, netplay, MEP, HD packs, Enhanced Synth) along with the four cores above. SMS is **not** Coleco: `SmsConsole` has `SmsModel::{Sms, GameGear, Sg, ColecoVision}` — Coleco is a slice (BIOS + ports + controller). SG-1000 stays.

SNES is the only coupling with a core that stays: Super Game Boy (`BaseCartridge` instantiates `Gameboy(..., true)`; `GbPpu` / `GbControlManager` include `SuperGameboy.h`). Cutting SNES requires cleaning up these hooks in GB, not deleting GB.

### Enums — do not renumber

`ConsoleType` already has explicit values (`Snes=0`, `Gameboy=1`, `Nes=2`, `PcEngine=3`, `Sms=4`, `Gba=5`, `Ws=6`). Deleting names without keeping explicit numbers on the ones that remain breaks settings/savestates of the live cores.

`CpuType` today is sequential (`Gameboy=7`, `Nes=8`, `Sms=10`, `Gba=11`). **Assign explicit values equal to the current ones** on the ones that remain. Gaps (0–6 SNES/coprocessors, 9 PCE, 12 WS) are not reused. The same for `MemoryType` / `DebuggerFlags` / `RomFormat` / `FirmwareType`: either a dead enumerant with a comment, or a stable explicit value. Never compact.

## Cuts — one PR per slice, in this order

Each PR on `main`. Green: compile (at least one platform), `clang-format`, `dotnet test UI.Tests`, `make unit-tests` / `core-unit-tests` if they exist in the tree. Don't mix slices.

### F1 — ColecoVision (cheap)

Doesn't change `ConsoleType`. `SmsModel::ColecoVision` disappears; `.col` stops loading.

- Core: `SMS/Input/ColecoVisionController.h`, `.col` branch in `SmsConsole::LoadRom`, `FirmwareHelper::LoadColecoVisionBios`, `RomFormat::ColecoVision`.
- Interop: `SetCvConfig`.
- UI: `CvConfig*`, `CvConfigView*`, `CvInputConfigViewModel`.
- Scripts: `SetCvConfig` in `headless_record.cpp`.
- Docs: README (Enhanced Audio "SMS-family" no longer mentions Coleco).

SMS / GG / SG-1000 and the SMS synth continue.

### F2 — WonderSwan

Isolated folder. Outside `Core/WS/` only `Emulator.cpp`, `Debugger.cpp`, and `ExpressionEvaluator.Ws.cpp`.

- Delete `Core/WS/` (~23 cpp, 55 entries in `Core.vcxproj`).
- Debugger: includes/switches for `CpuType::Ws` in `Debugger.cpp`, `DebugUtilities.h`, `Disassembler.cpp`, `MemoryDumper.cpp`, `ExpressionEvaluator.Ws.cpp`.
- Interop: `SetWsConfig`, `WsState`.
- UI: `WsConfig*`, `Ws*View*`, `WsDebuggerConfig`, `WsEventViewer*`, `WsStatusView*`, `WsRegisterViewer`, `WsDocumentation.json`, `WsIcon.png`.
- File dialog: `*.ws` / `*.wsc`.

### F3 — PC Engine

Own core (HuC6280, VDC/VCE, CD in `PCE/CdRom/`). Doesn't share a runtime CPU with NES; only `Base6502Assembler<PceAddrMode>` in the debugger.

- Delete `Core/PCE/` (~27 cpp, 61 entries in the vcxproj).
- Debugger: `PceDebugger`, `ExpressionEvaluator.Pce.cpp`, `Base6502Assembler` PCE template (the NES one stays).
- Interop: `SetPcEngineConfig`, `PceState`.
- UI: `Pce*` / `PcEngine*` (config, Avenue Pad input, debugger, `Pceas*` importers, `CheatDb` if there's a PCE one).
- File dialog: `*.pce` / CD.

### F4 — SNES + SGB (the big one)

- Delete SNES emulation (`SnesConsole`, PPU/APU, coprocessors SA-1, GSU, CX4, DSP, MSU-1, BS-X, ST018, SGB, SPC7110, SDD1, OBC1, Sufami). **Don't** delete the SNES pad: `SnesController` / `SnesMouse` / `SnesNttDataKeypad` move to `Core/Shared/Input/` for NES and the `ControllerHub`.
- `Emulator.cpp`: remove `TryLoadRom<SnesConsole>` and the include.
- Debugger: `SnesDebugger` and the `CpuType::{Snes,Spc,NecDsp,Sa1,Gsu,Cx4,St018}` in the switches in `Debugger.cpp` / `DebugUtilities.h` / disassembler / memory dumper / `ExpressionEvaluator.Snes.cpp` (and Cx4/Gsu/Spc/St018 if present).
- **GB:** remove `SuperGameboy.h`, `IsSgb()` / `GetSgb()` / `RunSgb` / `GameboyModel::SuperGameboy` / `AutoFavorSgb` / SGB firmware. GB handheld remains.
- Interop: `SetSnesConfig`, `SnesState`, Save SPC.
- System UI: SNES settings, SPC/GSU/SA-1 debugger, `SaveSpcFile*`, `CheatDb.Snes.json`, console icon. `SnesControllerView` / `SnesNttDataKeypadControllerView` **stay** (pad mapping).
- File dialog: `*.sfc` / `*.smc` / `*.spc`.

### F5 — docs and fork contract

- `CONTRIBUTING.md`: stop promising "merges stay cheap" in the wholesale-merge sense; clang-format/dotnet format style **continues** (cherry-picks). Prohibit Sync fork.
- README: system list = the four that remain; Enhanced Audio without Coleco/SGB.
- This plan → `Status: done` when F4 is green on `main`.
- DOX: `docs/AGENTS.md` already points to this file; if the cut changes ownership of `Core/`, update the root index.

## Shared surface (every PR touches this, for the slice's piece)

It's not "delete the folder and done":

| Place | What to cut per slice |
|---|---|
| `Emulator.cpp` `TryLoadRom<T>` | Snes / Pce / Ws (not Coleco) |
| `Core.vcxproj` + `.filters` | `SNES\` `PCE\` `WS\` entries + Coleco header |
| `InteropDLL/*ApiWrapper.cpp` | `SetSnesConfig` / `SetPcEngineConfig` / `SetWsConfig` / `SetCvConfig` |
| `UI/Interop/ConfigApi.cs` + `ConsoleTypeExtensions.cs` + `CpuTypeExtensions.cs` + `FirmwareTypeExtensions.cs` | dead cases |
| `FileDialogHelper.cs` | extensions |
| `EmuSettings` / `SettingTypes.h` | `SnesConfig`, `PcEngineConfig`, `WsConfig`, `CvConfig` structs — can be left empty for one version if serialization requires it; a stable tombstone is preferable |
| `Debugger.cpp` | the giant switch by `CpuType` |

## Out of scope

- Don't cut GBA (isolated core, outside synth/HD pack, but cheap compared to SNES).
- Don't cut SG-1000.
- Don't compact enums.
- Don't merge `upstream` into `main`.
- Don't reformat the whole tree "while we're at it".

## Verification per slice

```
# after each PR, from the repo root:
grep -R "ColecoVision\|ConsoleType::Snes\|ConsoleType::PcEngine\|ConsoleType::Ws\|TryLoadRom<Snes\|TryLoadRom<Pce\|TryLoadRom<Ws" --include='*.cpp' --include='*.h' --include='*.cs' Core UI InteropDLL
# F1: ColecoVision should go to zero; the other ConsoleTypes only go to zero in their corresponding slice.
```

Also: the file dialog doesn't list the cut extension; an NES ROM + a GB + an SMS + a GBA still load; clang-format + unit tests + Run tests on `main`.
