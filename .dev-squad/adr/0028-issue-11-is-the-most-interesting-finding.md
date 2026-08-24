# ADR-0028: Issue 11 is the most interesting finding in the set because it is the...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during auditor-b: Issue 11 is the most interesting finding in the set because it is the only one where task partitioning, not the problem domain, chose the architecture — and it is now committed (c18e54af, 'keep NES VGM tap inside NesApu.{h,cpp}'). NesApu permanently allocates six NesApuRegisterTap decorators and inserts one virtual dispatch in front of every $4000-$4013/$4017 write, for all users, recording or not, solely because a two-file task boundary forbade touching the five channel classes where a one-line tap would have gone. The critic's correctness verification of the decorator is sound and I did not find a counterexample. The concern is precedent: this is now the shape every future NES register instrumentation will copy, and its justification will not survive in the commit history. Either revisit it now that the T3 file boundary no longer binds (five one-liners, no allocations, no indirection), or record it as a deliberate standing pattern in an ADR. The general lesson for the workflow: when an actor reports that it chose a structure to stay within a declared file list, that is a signal to re-scope the task, not to accept the structure.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
