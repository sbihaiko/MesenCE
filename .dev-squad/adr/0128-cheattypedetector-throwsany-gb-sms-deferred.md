# ADR-0128: CheatTypeDetector parity tests use Assert.ThrowsAny; Gb/Sms support deferred

- Status: accepted (ThrowsAny change implemented 2026-08-29; product decision on Gb/Sms remains explicitly deferred)
- Date: 2026-08-27
- Consolidates: ADR-0069, ADR-0070

## Context
Phase 2 extracted the cheat-code type detection into
`UI/Logic/CheatTypeDetector.FromCode(ConsoleType, string)`. The extraction was a
behaviour-parity move (spec Risk Areas: assert current behaviour, do not fix
gaps), so the pre-existing quirk survived: unsupported consoles signal failure
with a bare `throw new Exception("Unsupported cheat type")`
(`UI/Logic/CheatTypeDetector.cs:30`), even though the `CheatType` enum declares
`GbGameGenie`/`GbGameShark`/`SmsGameGenie` members that no branch produces.

The new tests froze that contract more tightly than parity requires:
`UI.Tests/Cheats/CheatTypeDetectorTests.cs` uses `Assert.Throws<Exception>` for
`Gameboy` (line 52) and for `PcEngine`/`Sms`/`Gba`/`Ws` (line 62). xunit's
`Assert.Throws<T>` matches the exception type *exactly*, so these tests pin
the contract to the base `Exception` type rather than to "this throws". Any
later switch to a specific type (`NotSupportedException` carrying the
`ConsoleType`) — which the UI needs to surface a useful message — becomes a
test-touching change. ADR-0069 proposed loosening the tests together with that
later change; ADR-0070 argued the loosening is a one-line change now and a
test-touching change later, so it belongs in the parity phase itself.

## Decision
- [x] `UI.Tests/Cheats/CheatTypeDetectorTests.cs`: replace both
      `Assert.Throws<Exception>(...)` with `Assert.ThrowsAny<Exception>(...)`
      (lines 52 and 62). The parity statement ("unsupported consoles throw")
      is preserved exactly; the exception type is no longer part of the
      tested contract.
- [x] Keep `FromCode` unchanged in this step: no Gb/Sms branches, no
      exception-type change.
- Deferred product decision (not part of this ADR's checklist; needs its own
  follow-up when someone owns cheat support for GB/SMS): (a) whether
  `FromCode` should implement the `GbGameGenie`/`GbGameShark`/`SmsGameGenie`
  detection its enum already declares, and (b) whether unsupported consoles
  should throw `NotSupportedException` (with the offending `ConsoleType`) so
  the UI can show a specific message. Once the tests use `ThrowsAny`, (b) can
  land without touching the parity tests.

## Consequences
- The parity suite asserts the weakest statement that still captures current
  behaviour, which is the correct tightness for an extraction of a
  formerly-private quirk.
- The dead `CheatType` members remain a documented gap (test comment at
  `CheatTypeDetectorTests.cs:48-51`), not a hidden one.
- General rule for future parity extractions: how tightly the test is written
  decides how expensive the eventual fix is; prefer `ThrowsAny`/structural
  assertions over exact-type pins unless the exact type is the contract.

## Alternatives
- Keep `Assert.Throws<Exception>` and loosen it only when the exception type
  changes (ADR-0069's timing): rejected per ADR-0070 — pays a test edit later
  for no benefit now.
- Switch to `NotSupportedException` now: rejected — violates the parity
  requirement of the extraction phase and changes UI-visible behaviour without
  an owner.
- Implement Gb/Sms detection now: rejected — a product feature, out of scope
  of the test-infrastructure work; deferred as above.
