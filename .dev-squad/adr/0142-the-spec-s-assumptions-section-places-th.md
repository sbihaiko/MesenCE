# ADR-0142: The spec's Assumptions section places the first-run consent-dialog-sh...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during spec: The spec's Assumptions section places the first-run consent-dialog-showing code in EnhancementPacksWindow's code-behind (a Window class) but has it invoked from MainWindow's ROM-load hook via CommunityPackInstallService — i.e. a non-modal service path reaching into another window's code-behind, likely via a static method, just to pop a MesenMsgBox. CommunityPackConsentState's own docstring anticipates joint ownership between 'the caller (UI/Services/CommunityPackInstallService.cs + the settings window)', so this isn't a new decision, but the concrete wiring (does MainWindow call a static EnhancementPacksWindow method, or does CommunityPackInstallService show the dialog directly via MesenMsgBox and only persist the resulting flag through EnhancementPacksWindow-owned config code) is left to the actor's judgement.

## Decision
Consider having CommunityPackInstallService show the first-run consent dialog directly (it already owns DisplayMessageHelper-style notices and MesenMsgBox is a static show-from-anywhere API), with EnhancementPacksWindow.axaml.cs only reading/writing the same CommunityPackAutoInstallConsentGiven flag for the settings-window checkbox — avoiding a MainWindow -> EnhancementPacksWindow code-behind coupling.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
