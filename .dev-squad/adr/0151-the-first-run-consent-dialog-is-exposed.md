# ADR-0151: The first-run consent dialog is exposed as a public static method on ...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during Execute/T4: The first-run consent dialog is exposed as a public static method on a Window class (EnhancementPacksWindow) that is invoked from the ROM-load path without that window ever being instantiated. It works, and the spec explicitly sanctioned this placement ("the dialog-presentation code is kept alongside EnhancementPacksWindow's code-behind ... and is called from the ROM-load hook"), but the coupling is inverted: a background service now depends on a settings window type, and the config-mutation + Save side effect lives in the window layer rather than next to the flow that needs it.

## Decision
If this grows (extra prompts, per-pack consent, telemetry-free notices), move the presentation helper into UI/Services/ (e.g. CommunityPackConsentPrompt) and leave EnhancementPacksWindow owning only its own dialogs; UI/Logic/CommunityPackConsentState stays the host-free decision source either way.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
