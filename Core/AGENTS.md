# Core/ — DOX

## Purpose

C++ emulation cores (NES, GB/GBC, SMS/GG, GBA) and the shared services the
UI, `InteropDLL` and the headless harness under `scripts/` build on. This
file records the durable contracts of the pack recorder that other trees
consume; per-core emulation code follows the upstream Mesen 2 structure and
needs no local rules beyond the root DOX.

## Ownership

- `Core/NES/HdPacks/` — the bootstrap HD-pack builder and the sheet /
  pose recorder (`HdPackBuilder`, `SpriteGrouping`, `SheetRender`,
  `TileSheetTypes.h`). Decisions live in `docs/adr/` (ADR-0153, 0164,
  0170, 0171, 0173, 0174, 0177, 0179, 0181); this file only states the
  contracts a consumer relies on.
- `Core/Shared/HeadlessInput*` — the `input=<script>` engine the headless
  harness drives the emulator with (see `scripts/AGENTS.md`).

## Local Contracts

- **Per-frame hook.** `NesConsole` calls
  `HdPackBuilder::OnFrameEnd(const uint8_t buttons[2])` once per emulated
  frame; `buttons` is the packed button byte of ports 1 and 2 in
  `NesController::ToByte` order (bit 0 = A … bit 7 = Right). A standard NES
  pad supplies it directly, a SNES pad on an NES port supplies the eight
  buttons it shares with the NES pad, any other device or an empty port
  supplies 0. The bytes ride on the retained `MesenSheets::OamFrame`
  (`Buttons[2]`) and are **not** part of frame identity: a repeated frame
  keeps the buttons of its first occurrence (ADR-0181 §1).
- **`textures/sheets/poses.json`** is written by `SheetRender::SerializePoses`
  from `PoseStats` and nothing in it is computed at serialisation time.
  Optional fields a reader must tolerate being absent: per entry
  `fusionOf[]`, `next[]`, `variantOf`; top-level `cycles[]`, `sequences[]`
  (ADR-0179) and `input {frames, ports, held{}, never[]}` (ADR-0181 §2,
  written only when some button was ever held; `never` lists buttons and
  direction+action pairs no single port ever held at once). Consumers:
  `scripts/compose_engine.py` (`Poses`, `PoseInput`).
- **Save-time debug dumps**, env-gated, never pack files:
  `MESEN_SHEET_GRID_DUMP`, `MESEN_OAM_STREAM_DUMP` (per retained frame:
  index, repeat count, port 1 and 2 button bytes, then `node,x,y` per
  sprite) and `MESEN_POSE_TRACK_DUMP` (one ADR-0179 track per line as
  `frame:pose:held` triples in retained-frame indexes).
- Host-free rule (ADR-0127): `SpriteGrouping` and `SheetRender` take data
  and return data; file, env and log access stay in `HdPackBuilder`, so
  `scripts/core_unit_tests.cpp` can cover the rules without an emulator.

## Child DOX Index

- (none) — sub-trees follow this file and the root DOX.
