# ADR-0143: The first-run consent dialog is presented by the settings window's co...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during decompose: The first-run consent dialog is presented by the settings window's code-behind but is invoked from a ROM-load flow, when that window is typically not open. That makes a window code-behind act as an ambient dialog service and couples the Services layer to a specific Window type, which will be awkward to test and to reuse from any other trigger point.

## Decision
Move the dialog presentation into a small dedicated presenter under UI/Services/ (or a static helper next to DisplayMessageHelper) that owns the MesenMsgBox call and the sticky-flag write, leaving EnhancementPacksWindow with only the checkbox binding; UI/Logic/CommunityPackConsentState stays the sole decision authority.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
