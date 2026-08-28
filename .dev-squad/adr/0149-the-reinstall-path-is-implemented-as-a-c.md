# ADR-0149: The reinstall path is implemented as a client-side recursive Director...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during Execute/T2: The reinstall path is implemented as a client-side recursive Directory.Delete(outFolder, true) purely to satisfy the native installer's 'output folder is not empty' precondition. That puts the destructive step on the UI side of the interop boundary, where Core's unit tests cannot cover it and where a wrong container name turns into an unbounded recursive delete. ADR-0138 section 43 defines the reinstall gate but does not say who clears the folder.

## Decision
Give MepRecipeInstaller::Install an explicit replace/overwrite mode (install into a temp folder, then swap atomically, deleting only the paths the previous install's .mep-install.json recorded) and have the coordinator request that mode instead of deleting anything itself - keeping every mutation of a pack folder inside Core, next to the stamp that authorizes it.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
