# ADR-0070: xunit's Assert.Throws<T> matches the exception type exactly, so asser...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during auditor-b: xunit's Assert.Throws<T> matches the exception type exactly, so asserting Assert.Throws<Exception> pins the contract to the base Exception type rather than to 'this throws'. In a behavior-parity extraction, tests should assert the weakest statement that still captures current behavior (Assert.ThrowsAny<Exception>) — that satisfies the parity requirement identically while leaving a later switch to a specific exception type free. This is a one-line change now and a test-touching change later, so it is worth doing in this phase rather than deferring. The broader rule: a parity extraction turns a private quirk into a public tested contract, and how tightly the test is written decides how expensive the eventual fix is.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
