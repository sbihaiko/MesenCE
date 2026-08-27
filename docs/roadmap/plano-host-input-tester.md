# Plan — host input tester

**Status:** draft (2026-08-26) ·
**PRD:** none (host UX; not a pack/enhancement) ·
**Reference:** [hardwaretester.com/gamepad](https://hardwaretester.com/gamepad) ·
**Out of spec:** gamepad diagnostics on the host, not a pack format.
**Process:** the interop contract lives in this plan until it diverges from the code. No ADR required.

The remaining cores (NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA) are digital. Analog in Mesen means D-pad, tilt/accelerometer, and rumble — not FPS. Copying the Hardware Tester **in its entirety** is out of scope. Copy what closes the gap in host diagnostics.

A physical pad with an SNES layout (USB, 8BitDo, BlueRetro on the **host**) is a gamepad like any other in this tab. The `SnesController` console type (the 12-button protocol on the NES port) is a different layer — see `plano-reducao-cores.md`. The tester does not need SNES emulation.

## Success criteria

A user with a USB/Bluetooth pad connected, **with no ROM loaded**, opens
Settings → Input → the Test tab and sees:

- which devices Mesen can see (name, backend, `PadN` / `JoyN` slot);
- every button and axis live, with the **same keycode name** used in
  mapping (`Pad1 A`, `Pad1 LT Up`);
- the current deadzone ring over the sticks, and a warning if a resting
  stick isn't at (0,0);
- a button that triggers rumble on that pad.

The mapping window (`ControllerConfigWindow`) lights up the **console**
button whose keycode is pressed. Drift, wrong deadzone, and "Mesen doesn't
see my pad" no longer require the external site.

The in-game HUD (`InputHud`) remains the source of truth for the
**console**. This plan does not replace it.

## Three layers (do not mix)

| Layer | Where | What it shows | Today |
|---|---|---|---|
| 1. Host | XInput / DInput / evdev / GameController | Physical pad, raw axes, rumble | Only `[Input Connected]` logs |
| 2. Binarization | `IsPressed` + `ControllerDeadzoneSize` | `Pad1 X+` etc. after the deadzone | Invisible in the UI |
| 3. Console | `KeyMapping` → NES/GB/SMS/GBA | The system's A/B/Start | In-game HUD + a blind mapping window |

The Hardware Tester is layer 1. Mesen only exposes layer 3. The tester in
this plan is layer 1 + layer 2 (Mesen keycode), side by side.

## State of the ground (verified in code on 2026-08-26)

| Point | Status |
|---|---|
| Mapping UI | `ControllerConfigWindow` + `KeyBindingButton` + `GetKeyWindow` modal (25 ms poll, single-key picks the highest scancode) |
| Console HUD | `Core/Shared/InputHud.cpp` — digital buttons of the emulated device, optional overlay per port |
| Deadzone | Global 0–4 slider (`InputConfig.ControllerDeadzoneSize` → `GetControllerDeadzoneRatio()`), applied on the host when binarizing |
| Raw analog | `IKeyManager::GetAxisPosition` exists; used only in `GbMbc7Accelerometer` and `GbaTiltSensor` (both `TODO add configuration in UI`) |
| Pressed keys → UI | `InputApi.GetPressedKeys()` copies **at most 3** keycodes (`InputApiWrapper.cpp` + a buffer of 3 in `InputApi.cs`) |
| Pad identity | Name/vendor only in `MessageManager::Log`; bindings by **slot** (`Pad1`…), not by VID/PID |
| Rumble | `SetForceFeedback` on the host; global intensity; only on the pad that already sent input (`_enableForceFeedback`) |
| Linux hotplug | `LinuxKeyManager::UpdateDevices()` is a TODO; scans every 5 s |
| macOS | A pad without `extendedGamepad` is ignored |
| Presets | Xbox / PS4 / WASD / arrow keys in the setup wizard and the mapping window — stays as is |

## What not to copy

- Industry stats collection.
- Browser Gamepad API — native backends already exist.
- Tester as a replacement for mapping.
- Fighting-game-grade analog precision / circularity as a first-cut deliverable.
- Gyroscope, DualSense adaptive triggers.

## Phases

### I.0 — Host contract in the UI (blocks the rest)

The tester can't be built on top of the 3-slot `GetPressedKeys`. Expose
state **before** binarization, without changing the mapping model.

**Delivery:** the UI queries the pad list and live state without truncation.

New interop (provisional names — adjust to match `InputApi`'s style):

- `GetConnectedGamepadCount()` / `GetConnectedGamepadInfo(index, out InteropGamepadInfo)`
  - `Name`, `Backend` (`XInput` / `DirectInput` / `Evdev` / `GameController`), `SlotLabel` (`Pad1` / `Joy2`), `VendorId`, `ProductId`, `HasRumble`
- `GetGamepadState(index, out InteropGamepadState)`
  - digital buttons (pressed + keycode + `GetKeyName`)
  - **raw** `int16` axes (sticks LX/LY/RX/RY, triggers L2/R2), no deadzone
- `TestForceFeedback(index, durationMs)` — ignores `_enableForceFeedback` for the test

Files: `IKeyManager` (+ `Windows` / `Linux` / `MacOS` impls), `InteropDLL/InputApiWrapper.cpp`, `UI/Interop/InputApi.cs`.

Don't break `GetPressedKeys` (Lua, `GetKeyWindow`, `ShortcutKeyHandler`,
`StateGrid`). Extend it or add a parallel API.

Raw axes **do not** go through the deadzone. The UI draws the ring using
the current slider.

### I.1 — Test tab in the Input config

**Delivery:** Settings → Input gains a **Test** tab (next to General /
Display). No ROM. No modal.

Per connected pad:

- identity (name, backend, Mesen slot, VID/PID if available);
- a generic/Xbox silhouette with buttons lighting up;
- two stick circles + a live dot + the deadzone ring (`ControllerDeadzoneSize`);
- L2/R2 bars;
- a list of the active Mesen keycodes (`Pad1 A`, `Pad1 X+`);
- a warning if a resting stick is off ~0 (drift);
- a Test rumble button.

New ViewModel: data via `Refresh(...)` injected by the code-behind / timer
— the constructor **does not** call `InputApi` (Phase 3 contract from
`UI/AGENTS.md`). Do not extract into `UI/Logic/` (depends on native
interop). Timer ~16–33 ms only while the tab is visible.

Poll: `InputApi.UpdateInputDevices()` on tab open.

### I.2 — Live highlight in the mapping window

**Delivery:** with `ControllerConfigWindow` open, the `KeyBindingButton`
whose `KeyBinding` is in `GetPressedKeys` (or the new API) lights up.
Clicking to rebind is still required.

Does not replace `GetKeyWindow`. It complements it: the user sees *which*
console button the pad is triggering **before** rebinding.

### I.3 — Follow-ups (out of the first cut)

Suggested order, each one independent:

1. Per-device deadzone (the I.1 preview already justifies the global slider).
2. Binding by VID/PID instead of slot `Pad1` (hotplug stops breaking mapping).
3. UI for the MBC7 / GBA tilt axes (the two TODOs).
4. Circularity test (a stick that never leaves the deadzone).
5. Linux: a real `UpdateDevices()`. macOS: don't discard a pad without
   `extendedGamepad`.

## Out of this plan

- Redesign of the Xbox/PS4/WASD presets.
- In-game HUD overlay (layer 3).
- Special devices (Zapper, Power Pad, Phaser, tablet) — the tester is for
  **host gamepads**.
- Automatic remapping from the tester.

## Verification

Plans have no automated check (`docs/AGENTS.md`). Close each phase with:

| Phase | Check |
|---|---|
| I.0 | Build Core+Interop+UI on the three target platforms; Lua `emu.getPressedKeys` and the keyboard shortcut unchanged; `GetGamepadState` returns axes with the stick in the corner (not just 0/1) |
| I.1 | Manual: 0 pads → empty state; 1 Xbox/generic pad → buttons, sticks, deadzone, rumble; 2 pads → two panels; the deadzone slider moves the ring live |
| I.2 | Manual: NES/GB/GBA/SMS mapping — pressing the pad lights up the already-bound console button; rebinding via the modal still works |
| Drift | Stick with visible drift in the tester at rest; if within the deadzone, the in-game HUD **does not** light up the D-pad |

There is no test ROM for I.0–I.2. I.3 tilt/MBC7 uses a ROM with a sensor
when that phase starts.
