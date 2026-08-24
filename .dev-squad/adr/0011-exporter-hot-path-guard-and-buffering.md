# ADR-0011: Exporter hot path — per-console cached flag when idle, buffered writes when recording

- Status: accepted
- Date: 2026-08-24

## Context
Raised during spec and auditor-b (consolidates former ADR-0025 and ADR-0026): F1.1's VGM tap sits at a materially hotter call site than any existing Enhanced Audio instrumentation — the chip Write/WriteRam methods fire on every CPU-driven I/O access, versus the existing tap that samples once per MixAudio flush (~179Hz). The audit confirmed two concrete problems. (1) Header/code mismatch: none of the six call sites actually guard with IsRecording(), despite VgmExporter.h claiming they do — the idle cost is nonetheless small (out-of-line static call + pointer load + branch). (2) The larger, unmeasured cost is the recording-active path: every register write takes a SimpleLock, copies a shared_ptr (atomic refcount pair), and issues several unbuffered ofstream::put calls from the emulation thread. Additionally, this concern pulls against the per-emulator ownership of ADR-0012: reaching the exporter through _console->GetSoundMixer()->... is a multi-hop pointer chase on the same hot path. Both are right about their own axis; the tension must be resolved deliberately, not by whichever task lands last.

## Decision
Reconcile ownership and hot-path cost with a per-console cached raw pointer or relaxed atomic flag held by the chip object itself, refreshed when recording starts/stops — emulator-scoped ownership (ADR-0012) with a single-load hot path. Fix the header/code mismatch by actually implementing the documented guard at every call site, so the no-recording steady state is a single branch. On the recording path, buffer command bytes into a vector flushed off the hot path (e.g. at the audio flush cadence) instead of per-access unbuffered ofstream::put.

## Consequences
Idle cost: one relaxed load + branch per chip write. Recording cost: no lock, no refcount traffic, no per-write I/O on the emulation thread. Deciding this before the remaining console wiring (GB/SMS) keeps it a one-time change instead of six retrofits.

## Alternatives
Process-global flag read (cheapest, but conflicts with per-emulator ownership and multi-instance correctness). Leave call sites unguarded (measurable overhead in the hottest emulation path for all users). Keep per-write disk puts (risks audible stalls under recording).
