# Slice 2 — Core/ non-Debugger (NES · SMS/GB · Shared · Netplay) — inherited-code review

- Repo `HEAD` reviewed: `2c58e139`; merge-base `73be5b58`.
- Scope: `Core/NES/`, `Core/NES/Loaders/`, `Core/Gameboy/`, `Core/SMS/`, `Core/GBA/`, `Core/Shared/`, `Core/Netplay/` (~650 tracked files). Console cores' own C-tier files (GbPpu base, GbaCpu/Ppu/MM, SmsCpu/Vdp base, APU/DMA logic) plus the fork's B/A additions (HD tile capture/replacement, enhanced synth, MEP zip/recipe, netplay wire) sampled.
- Method: tier/heat snapshot, grep over the ROM/disk-format loaders and wire-protocol parsers (untrusted-input boundary), targeted reads; fork-owned A-tier clusters confirmed already hardened (prior MEP/HdPack work).

## Findings

21 total — P0 0, P1 3, P2 17, P3 1. Tiers: B 5, C 16. Exploitable: 0 (all need a local file the user loads, or a rogue netplay peer the user already joined).

## Patched (6 findings, 6 files, +38/−3, 4 commits)

| file | tier/heat | finding(s) resolved | hunk gist | ± |
|---|---|---|---|---|
| `Core/Netplay/NetMessage.h` | C h=1 | [P1] `length==0` → `_receivedData.write(len-1)=0xFFFFFFFF` ~4 GB OOB read/alloc on client **and** server | reject length 0 (type 0xFF) | +9/−2 |
| `Core/Netplay/GameClientConnection.cpp` | C h=3 | [P1] wire `uint8` port ≥ `PortCount` indexes `_inputData[8]` OOB deque write | `port >= BaseControlDevice::PortCount` → ignore | +5/−0 |
| `Core/Netplay/PlayerListMessage.h` | C h=1 | [P2] rogue-server `playerCount` → ~16 GB `resize` | cap at 64 | +4/−0 |
| `Core/Shared/SaveStateManager.cpp` | C h=2 | [P2] crafted `.mss` `frameBufferSize`/`nameLength` → near-4 GB allocs | 2 MiB / 1 MiB caps | +9/−0 |
| `Core/NES/Loaders/StudyBoxLoader.cpp` | C h=0 | [P2] PAGE/AUDI chunk headers over-read under weak `< end-4` guard | require `end-data >= 12`/`>= 8` | +12/−0 |
| `Core/SMS/SmsConsole.cpp` | B h=2 | [P2] `1 << (power+1)` signed-shift UB > 2^30 | `1u <<` | +1/−1 |

Commits: `e30dd9c0` (netplay), `a766d434` (save state), `50f339e0` (StudyBox), `e58aec16` (SMS pad).

## Reported, not patched (15)

Netplay / Shared:
- `Core/Netplay/GameServer.cpp:33` [P2 C race] `_openConnections.push_back` (server thread) races emu-thread iteration — realloc/UAF.
- `Core/Netplay/GameClientConnection.cpp` [P2 C leak] per-port deque still grows unbounded when a valid port is never drained (invalid-port case now rejected, so only a peer that *owns* the port can feed it).
- `Core/Netplay/GameConnection.cpp:44` [P3 C] `messageLength` in `(MaxMsgLength-4, MaxMsgLength]` can never complete → stall.

NES loaders (all C, hot in upstream):
- `Core/NES/Loaders/NsfeLoader.h:131` [P1] NSFE time/fade chunk indexes `int32[256]` unbounded → OOB past header on crafted file.
- `Core/NES/Loaders/NsfeLoader.h:95` [P2] INFO chunk fixed-length reads without chunk-length guard.
- `Core/NES/Loaders/iNesLoader.cpp:80` [P2] `prgSize+chrSize` wraps in uint32 → passes bound, OOB GetCRC.
- `Core/NES/Loaders/iNesLoader.cpp:20` [P2] 15-byte minimum lets a 16-byte header memcpy / `dataSize` underflow.
- `Core/NES/Loaders/NsfLoader.cpp:158` [P2] no 0x80 min gate → OOB walk + underflowed insert.
- `Core/NES/Loaders/UnifLoader.cpp:88` [P2] non-hex 4th chunk char leaves `chunkNumber` uninitialized → OOB index into `[16]` arrays.
- `Core/NES/Loaders/FdsLoader.cpp:121` [P2] case-3 block reads `diskSide[i+13/+14]` pre-bounds.

Console HD provenance (B-tier, latent; the agent verdict is "fragile, needs a recorded-footage/runtime validation", not a proven bug — deferred, not silent):
- `Core/Gameboy/GbxFooter.h:46` [P2 C+hot] `Init()` pointer-arithmetic underflow on sub-56-byte vectors (only caller `>=0x120` guards).
- `Core/SMS/SmsVdp.cpp:613` [P2 B] HD-info entry zeroed *before* the forced-blank/masked/cram-dot guard.
- `Core/SMS/SmsVdp.cpp:83` [P2 B] `SetHdPack()` pins `_hdScreenInfoBuffers[0]` unsynced to the color buffer in flight.
- `Core/Gameboy/GbPpu.cpp:976` [P2 B] HD-info re-sync only inside the first-allocation branch.
- `Core/Gameboy/GbPpu.cpp:964` [P2 B] DMG translucent-sprite backdrop color derived from the wrong palette when `DisableBackground` is set.

## Verification

Core builds clean; core-unit-tests 523 PASS at baseline, mid-slice and final. No behavioral test touched (guards only). Full suite green — see final report.

## Before / after (0–10)

| axis | before | after | supporting numbers |
|---|---|---|---|
| quality | 6 | 7.5 | 6/21 patched; the two remote-reachable P1s (netplay OOB) closed with 5–9-line guards; 15 kept reported for tier-C-hot or latent-reason reasons |
| performance | 8 | 8 | netplay guards are one compare per message; loader guards one compare per chunk — no hot-loop change |
| readability | 7 | 7 | +38/−3, entirely additive guards with inline comments ("ignore input for an invalid port") |
| security | 5 | 6.5 | before: crash/OOB from a second 5-byte packet on any client *and* server, OOB port deque write, ~16 GB resize; after: those three reachable paths bounded; remote file-format parser P1s (NSFE) remain reported because the loaders are upstream-hot tier C |
