# ADR-0113: Issues 2 and 6 conflict with issues 7/9/11 and are noise produced by ...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: none — process lessons (defect-fix specs carry a reproduction; unverified critic issues are unranked); retired as ADRs, see ADR-0132 Alternatives

## Context
Raised during auditor-b: Issues 2 and 6 conflict with issues 7/9/11 and are noise produced by the false premise. Both ask for an explicit decision on whether the `DefaultTile` wildcard entry survives beside real palette variants — but the code already did exactly what they recommend, both before and after the change: AddRomTiles/AddPrgScanTiles write the wildcard into `_tilesByKey` (HdPackBuilder.cpp:208, :280) and leave the DefaultTile entry in `_hdData.Tiles`, while ProcessTile appends palette-specific entries alongside it. No contract changed, so no decision was needed. When critics reason from a spec narrative rather than from the code, they manufacture decisions that do not exist; treat any critic issue that does not cite a verified line of behavior as unranked until confirmed.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
