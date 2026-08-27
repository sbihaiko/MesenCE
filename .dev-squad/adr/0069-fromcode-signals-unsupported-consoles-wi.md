# ADR-0069: FromCode signals unsupported consoles with a bare `throw new Exceptio...

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0128

## Context
Raised during Execute/T2: FromCode signals unsupported consoles with a bare `throw new Exception("Unsupported cheat type")`, and the new tests now freeze that contract for Gameboy, PcEngine, Sms, Gba and Ws - even though CheatType declares GbGameGenie/GbGameShark/SmsGameGenie members that no branch can produce. Behavior parity was the explicit T2 requirement (spec Risk Areas: assert current behavior, do not 'fix' the gap), so this is correct for this task, but the extraction turned an inline private-method quirk into a tested public contract that is now more expensive to change.

## Decision
In a follow-up phase, decide whether the detector should (a) support the Gb/Sms branches its own enum already declares, and (b) throw a specific exception type (e.g. NotSupportedException carrying the offending ConsoleType) so the UI can surface a useful message instead of a generic failure. Loosen the tests to Assert.ThrowsAny<Exception> at the same time.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
