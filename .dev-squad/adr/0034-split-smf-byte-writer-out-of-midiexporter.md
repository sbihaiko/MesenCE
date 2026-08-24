# ADR-0034: Split the SMF byte-writer out of MidiExporter — the 200-line guardrail's headroom is spent

- Status: accepted
- Date: 2026-08-24

## Context
Raised during auditor-b (consolidates audit-round ADR-0028, id from the reused 0022–0032 range): the 200-line-per-file guardrail was satisfied by relocating prose rather than by decomposing, and it has now boxed the file in. MidiExporter.cpp sat at 198/200 lines at audit time and has since grown to 227 — already past the cap — while MidiExporter.h is 163 lines that are mostly rationale comments. Both accepted remediations (open/validate the ofstream in the constructor per ADR-0033, extract the AdvanceTick() tick seam per ADR-0013) add ~10 lines to a file that cannot take them, so the guardrail — not the design — would dictate the next change. The relocation has also already drifted: the header's timing section says 'see AdvanceTick()' but no such member exists (the tick math is inlined at MidiExporter.cpp:32-36), and the header still includes <chrono>, which the .cpp never uses — residue of the uniform mirroring diagnosed in ADR-0035.

## Decision
Treat 'move the prose to the header' as a one-time escape hatch that has been spent. The next edit to MidiExporter splits the SMF byte-writer (WriteVarLen/AppendDelta/AppendBytes/EmitEvent/WriteFile) out of the note state machine into its own file, moves the corresponding rationale comments next to the code they describe, and removes the unused <chrono> include. The ADR-0013 and ADR-0033 changes land on top of (or together with) this split, not squeezed under the cap.

## Consequences
Restores headroom for the accepted fixes, gives the rationale comments a file whose code they actually sit next to, and closes the AdvanceTick()/<chrono> doc-code drift. One extra file in Core and in the makefile/vcxproj manifests (see the drift guard in ADR-0007).

## Alternatives
Grant the file a guardrail exception: leaves the doc drift and keeps prose-relocation as the go-to dodge. Keep relocating prose to the header: already demonstrably drifting from the code.
