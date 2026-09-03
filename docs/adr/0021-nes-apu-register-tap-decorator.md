# ADR-0021: Inline the NES APU register taps; drop the NesApuRegisterTap decorator

- Status: accepted
- Date: 2026-08-24

## Context
Raised during Execute/T3 and auditor-b (consolidates former ADR-0028 — first-round id, since retired and reissued; see ADR-0035): The NES tap is implemented as a NesApuRegisterTap decorator that NesApu inserts between NesMemoryManager and each of its six channel objects (SquareChannel x2, TriangleChannel, NoiseChannel, DeltaModulationChannel, ApuFrameCounter), committed as c18e54af. This permanently allocates six heap objects and adds one virtual dispatch in front of every $4000-$4013/$4017 write, for all users, recording or not — adopted (per the actor's own write-up) primarily to keep the change inside the task's declared two-file list, after a first attempt that put a one-line tap in each channel's WriteRam. The decorator is verified correct (INesMemoryHandler's four virtuals all forwarded; GetMemoryRanges forwards allowOverride; nothing compares registered handler pointers against the APU channels; DebugWrite's `handler == _mapper` check reads from _ramReadHandlers where the channels never appear). The concern is precedent: task partitioning, not the problem domain, chose this architecture, its justification will not survive in commit history, and it is the shape every future NES-side register instrumentation will copy.

## Decision
Inline the taps: put the VgmExporter log call directly in each channel's WriteRam (SquareChannel, TriangleChannel, NoiseChannel, DeltaModulationChannel, ApuFrameCounter — five one-liners) and remove the NesApuRegisterTap decorator from NesApu.h/cpp. Rationale for choosing this side: the ADR-0011/0012 remediation already has to touch the same call sites (real IsRecording() guard, per-console cached flag), so the multi-file cost is paid regardless, while keeping the decorator would preserve a permanent virtual dispatch on the hottest NES I/O path with no remaining benefit — the T3 file boundary that motivated it no longer binds. Workflow lesson stands: when an actor reports that it chose a structure to stay within a declared file list, that is a signal to re-scope the task, not to accept the structure.

## Consequences
Inlining removes six allocations and a virtual hop from the hottest NES I/O path and touches five files once. Future NES-side register instrumentation copies the inlined one-liner shape, not a decorator.

## Alternatives
Keep the NesApuRegisterTap decorator as the standing NES instrumentation pattern (rejected): preserves the two-file locality and gives future instrumentation a single seam, but at a small permanent dispatch cost on every APU write for all users, and its only real justification was a task file boundary that no longer binds. Leave it undecided: the next instrumentation task copies whichever shape it finds, and the pattern ossifies without ever having been chosen.
