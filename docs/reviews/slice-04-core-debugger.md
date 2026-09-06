# Slice 4 — Core/Debugger/ — inherited-code review

- Repo `HEAD` reviewed: `2c58e139`; merge-base `73be5b58`.
- Scope: `Core/Debugger/**` — ExpressionEvaluator (all consoles), Disassembler, BreakpointManager, ScriptingContext/LuaApi/LuaCallHelper, PpuTools, Debugger state get/set, callstack/stepback, CDL, trace, label/workspace.
- Method: two parallel sweeps (Lua/scripting; debugger/ppu-tools/types) folded into one finding set. Tier picture: nearly everything C + upstream-hot (report-only); only ExpressionEvaluator/Disassembler/Debugger/MemoryDumper etc. are B (fork-modified by the console removal).

## Findings

9 total — P0 0, P1 1, P2 7, P3 1. Tiers: B 3, C 6. Exploitable: 0. Confirmed the expected "mostly report, near-zero patches" shape: **no memory-safety bug reachable from an unmodified running ROM** (no debugger window/CDL) was found.

## Patched (2 findings, 1 file, +8/−6, 1 commit)

| file | tier/heat | finding(s) resolved | hunk gist | ± |
|---|---|---|---|---|
| `Core/Debugger/ExpressionEvaluator.cpp` | B(hot) | [P2] `<<`/`>>` shift count ≥ 64 or negative (C++ UB) on breakpoint/trace path; [P2] signed int64 overflow UB in `*/+/-`/unary `-` (`9223372036854775807 + 1`) | do arithmetic on `uint64_t` (two's-complement wrap), mask shift count `& 0x3F` | +8/−6 |

Commit: `9fcc5b48`.

## Reported, not patched (7)

C+hot (report-only; none judged exploitable):
- `Core/Debugger/LuaApi.cpp:623` [P1] `emu.drawPixels` int `width*height` unvalidated → negative/wrapped alloc = crash across the Lua C boundary or heap OOB read.
- `Core/Debugger/PpuTools.cpp:212` [P2] `InternalGetTileView` reads plane past region when tiles straddle/`srcSize` column extends.
- `Core/Debugger/ScriptingContext.cpp:308` [P2] `UnregisterMemoryCallback` frees a still-registered registry slot → later callback invokes an unrelated function.
- `Core/Debugger/LuaCallHelper.cpp:100` [P2] float-fallback tests top-of-stack instead of `index` → float args read as 0.
- `Core/Debugger/BreakpointManager.h:51` [P2] `Idle=9` operation would index the 9-wide bucket arrays OOB (latent — no current path observed).
- `Core/Debugger/LuaApi.cpp:474` [P3] failed callback registration leaks a Lua registry slot (repeatable → exhaustion).

B (patchable by rule, not selected — torn-read on the hot emu-thread state path needs a design decision, not a hunk):
- `Core/Debugger/Debugger.cpp:756` [P2 race] `GetCpuState/GetPpuState` copy the live per-console state with no `DebugBreakHelper`/sync while the setters all break first.

Not filed as defects: a busy-spin-without-yield in `DebugBreakHelper.h` and the stale SNES references left by the fork's console removal.

## Verification

C++ core builds clean; the evaluator change is exercised by the 523 core-unit-tests (evaluator/expression suites) at the final run — all PASS. Full suite green — see final report.

## Before / after (0–10)

| axis | before | after | supporting numbers |
|---|---|---|---|
| quality | 6.5 | 7 | 2/9 patched (both C++-UB items in the one B file this slice owns); the P1 `emu.drawPixels` stays reported (C+hot) |
| performance | 8 | 8 | two extra ops (`& 0x3F`, unsigned math) on the breakpoint-expression path only — not frame or trace hot loop |
| readability | 7 | 7.5 | +8/−6 in one file with a comment explaining *why* the math is unsigned ("so signed overflow wraps instead of invoking UB") |
| security | 5.5 | 6.5 | before: UB shifts/overflow could miscompile the evaluator on breakpoint/trace expressions; after: evaluator arithmetic defined; the remaining C+hot Lua/PPU-tools P1/P2s are reported, not fixable without widening the merge surface |
