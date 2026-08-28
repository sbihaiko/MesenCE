# ADR-0160: CONFIRMED, MEDIUM, but a larger change than the others (issue 8). `Cl...

- Status: proposed
- Date: 2026-08-28

## Context
Raised during auditor-b: CONFIRMED, MEDIUM, but a larger change than the others (issue 8). `ClearFolderForReinstall` does `Directory.Delete(outFolder, true)` on the UI side of the interop boundary, purely to satisfy `MepRecipeInstaller::PrepareOutputFolder`'s non-empty precondition, and swallows IOException/UnauthorizedAccessException silently. Two real mitigations already exist in the same file (the sanitization and the rooted-path assertion in `ResolveOutFolder`), so this is not an unbounded-delete-today bug; the legitimate point is that ADR-0138 §43 defines the reinstall gate without saying who clears the folder, and the destructive step sits where Core's unit tests cannot reach it. Prefer giving `MepRecipeInstaller::Install` an explicit replace mode (temp folder + atomic swap, deleting only paths the previous `.mep-install.json` recorded) so every pack-folder mutation lives next to the stamp that authorizes it. Sequence it after the container-name extraction, which makes the key derivation testable first. Not a blocker for F6.4b.

## Decision
(to be decided — proposed for human review)

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
