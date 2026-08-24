# ADR-0011: F1.1's VGM tap sits at a materially hotter call site than any existin...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during spec: F1.1's VGM tap sits at a materially hotter call site than any existing Enhanced Audio instrumentation: these Write/WriteRam methods fire on every CPU-driven I/O access to the chip, versus the existing Enhanced Audio tap which only samples state once per MixAudio flush (~179Hz). This is a new class of performance-sensitive integration point in the codebase, not just a variation on the existing pattern.

## Decision
Actor should gate each tap behind a cheap 'is VGM recording active' check (e.g. an atomic bool or existing IsRecording()-style flag read before any timestamp/serialization work) so the no-recording steady-state cost is a single branch, not a virtual call or lock, in the hottest emulation path.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
