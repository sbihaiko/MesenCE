# ADR-0039: No-Intro SHA-1 computed from the ROM file, per system, before the console exists

- Status: accepted
- Date: 2026-08-24
- Phase: F3.0 (MEP v1 host)

## Context
MEP matches packs by No-Intro SHA-1 (MEP-v1 §4): the hash of the ROM payload,
not of the file. The core has `Emulator::GetHash(Sha1)` (whole file) and
`NesConsole::GetHash(Sha1Cheat)` (PRG only) — neither is No-Intro, and both
need a mounted console. The MEP manager must resolve matching packs *before*
`console->LoadRom`, because NesConsole/Gameboy/SmsConsole load their HD packs
inside their own LoadRom.

## Decision
`MepPackManager::ComputeNoIntroSha1(VirtualFile& romFile)` is a static
function working on the file bytes alone. The hashed range is chosen by file
extension/signature, following the spec table:

| file | hashed range |
|---|---|
| `.nes` with `NES\x1A` magic | skip 16-byte header, skip 512-byte trainer when flags6 bit 2 is set |
| `.sfc/.smc/.swc/.fig/.bs/.st` | skip 512-byte copier header when `size % 1024 == 512` |
| everything else (`.gb/.gbc/.sms/.gg/.sg/.col/...`) | whole file |

Amended by ADR-0044 item 1 (MEP-v1 §4, v1.1): for iNES the hashed range is
clamped to the header-declared PRG+CHR size, so trailing garbage after the
payload no longer changes the hash; the trainer skip is unchanged.

Output is 40 uppercase hex digits (matches `SHA1::GetHash`). Comparison with
`targets[].sha1` is case-insensitive. `crc32` is not used for matching in v1
(spec allows it only as a pre-filter).

## Consequences
- Matching runs once per `Emulator::InternalLoadRom` after the optional IPS/
  BPS patch is applied, so a pack targets the *patched* ROM hash — the same
  behaviour users get from `HdPacks/<rom>/hires.txt` patch handling.
- An `.nes` file without the iNES magic (e.g. UNIF) is hashed whole; UNIF
  packs are unsupported until No-Intro publishes a rule for them.
- Cheap: one SHA-1 over a buffer already in memory.

## Alternatives
- Ask the mounted console for the hash: impossible at the required point in
  the load sequence without restructuring every console's LoadRom.
- Match by file name (like HdPacks/): rejected by the spec and by the PRD —
  the pack must survive renames and identify the exact revision. Revised:
  MEP-v1 v1.1 §2.1 rule 5 and ADR-0049 re-admitted name matching for the
  convention forms (sibling folder, `<Game>.zip`); hash matching remains the
  rule for `pack.json` containers.
