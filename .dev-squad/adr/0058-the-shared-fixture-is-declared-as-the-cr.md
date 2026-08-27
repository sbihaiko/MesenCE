# ADR-0058: The shared fixture is declared as the cross-language contract for the...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0124

## Context
Raised during Execute/T3: The shared fixture is declared as the cross-language contract for the future Fase 4B C++ suite, but the control-character cases (< 0x20) are deliberately excluded from it and tested only via C# [InlineData] escape sequences. The C++ suite reading this fixture will therefore get zero coverage of the control-char rule, which is the one rejection MepZipValidator adds beyond the old inline UI check — the exact rule most likely to drift between the two implementations.

## Decision
Either extend the fixture format with an escape convention (e.g. a third column or \xNN escapes in the path column, documented in the header) so control-char cases live in the shared file, or record explicitly in the fixture header that control-char parity is owned by each suite separately and must be duplicated in the C++ suite.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
