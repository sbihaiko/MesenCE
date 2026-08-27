# ADR-0106: The F5.4b spec is built on a misdiagnosis. The 'DefaultTile wildcard ...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during Execute/T1: The F5.4b spec is built on a misdiagnosis. The 'DefaultTile wildcard funnel' in HdPackBuilder::ProcessTile does not exist — the wildcard key is only ever written to `_tilesByKey` (HdPackBuilder.cpp:206, :278), never to `_tileUsageCount`, so the old fallback lookup was unreachable and palette variants were already captured unbounded (measured: up to 71 distinct palettes for one tile shape on Zelda.nes). The real open question for ADR-0050 step (b) is therefore not capture-side promotion but a variant-budget policy: how many palette variants per shape are worth persisting, and what the pack-size/quality trade-off is at load and draw time.

## Decision
Re-scope F5.4b: record that NES bootstrap capture is already palette-specific and unbounded, and turn step (b) into an explicit decision on the per-shape variant budget (cap value, selection rule for which variants to keep — e.g. highest-usage rather than first-8/last-seen — and whether the cap is per session or per pack). Any cap that lowers today's capture fidelity needs its own ADR with before/after pack-size and coverage numbers, plus a validator that fails when the wrong variants are dropped.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
