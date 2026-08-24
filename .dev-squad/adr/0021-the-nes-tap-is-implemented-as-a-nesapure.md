# ADR-0021: The NES tap is implemented as a NesApuRegisterTap decorator that NesA...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during Execute/T3: The NES tap is implemented as a NesApuRegisterTap decorator that NesApu inserts between NesMemoryManager and each of its six channel objects (SquareChannel x2, TriangleChannel, NoiseChannel, DeltaModulationChannel, ApuFrameCounter). This is a permanent structural change to the NES memory-map wiring - six extra heap-allocated objects and one extra virtual dispatch on every $4000-$4013/$4017 write - adopted (per the actor's own write-up) primarily to keep the change inside the task's declared two-file list, after a first attempt that put a one-line tap in each channel's WriteRam. The decorator is correct (INesMemoryHandler has exactly four virtuals and all four are forwarded; GetMemoryRanges forwards allowOverride; nothing in the codebase compares registered handler pointers against the APU channels, and DebugWrite's `handler == _mapper` check reads from _ramReadHandlers where the APU channels never appear), but it is a design choice driven by task partitioning rather than by the NES core's own layering, and it will be the shape every future NES-side instrumentation inherits.

## Decision
Either accept the decorator as the standing pattern for NES register instrumentation and document it as such, or revisit it once the T3 file boundary no longer applies and put the tap directly in each channel's WriteRam (five one-liners, no indirection layer, no extra allocations). Decide deliberately rather than letting the scope-driven choice become the de facto architecture.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
