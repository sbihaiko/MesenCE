# ADR-0148: The "Core/ stays HTTP-free" invariant (ADR-0138 §37) is enforced by a...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during Execute/T3: The "Core/ stays HTTP-free" invariant (ADR-0138 §37) is enforced by a source-text grep with a hand-rolled comment stripper. That is cheap and readable, but it is a lexical approximation of a build-level property: it cannot see HTTP reached through a transitive include, a third-party wrapper under Dependencies/, or a differently-named client class, and it can be defeated by string-literal edge cases in the stripper. The invariant it guards is the whole network boundary for the community-pack flow.

## Decision
Keep the grep as the fast pre-commit signal, but consider backing it with a build-level assertion — e.g. assert that the Core static lib's link inputs and resolved include graph contain no curl/HTTP symbols — so the boundary is proven by the toolchain rather than by pattern matching. Worth an ADR only if the boundary is expected to come under real pressure.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
