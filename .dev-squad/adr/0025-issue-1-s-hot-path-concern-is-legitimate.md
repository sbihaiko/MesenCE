# ADR-0025: Issue 1's hot-path concern is legitimate but its premise is already h...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: Issue 1's hot-path concern is legitimate but its premise is already half-satisfied, and it misidentifies which cost matters. Verified: none of the six call sites actually guard with IsRecording() despite VgmExporter.h claiming they do ('guarded by IsRecording() so it's a no-op otherwise') — a header comment that documents behaviour the code does not have. The idle cost is nonetheless small: an out-of-line static call plus a non-atomic pointer load plus a branch. The larger unflagged cost is the recording-active path, where every single CPU-driven register write takes a SimpleLock, copies a shared_ptr (atomic refcount pair), and issues several unbuffered ofstream::put calls from the emulation thread. That is the configuration where a user will actually notice, and it is the one nobody measured. Fix the header/code mismatch, and buffer command bytes into a vector flushed off the hot path rather than putting bytes to disk per I/O access.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
