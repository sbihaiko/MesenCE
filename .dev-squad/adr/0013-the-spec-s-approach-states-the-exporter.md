# ADR-0013: The spec's approach states the exporter receives 'endereço/porta + va...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: The spec's approach states the exporter receives 'endereço/porta + valor + timestamp de amostra', but T1's proposed signature is LogWrite(chip, addr/port, value) with no timestamp. VGM encodes timing as explicit wait commands between register writes; with no caller-supplied sample position or cycle count, the exporter has to invent timing (wall clock, or one wait per write), which yields a file that plays at the wrong tempo — and this is exactly the class of defect the spec's own risk section says cannot be caught by grep + make core.

## Decision
Include the timing source in the contract — e.g. LogWrite(chip, addr, value, uint64_t masterClock) with the exporter converting to 44100Hz VGM samples, or an explicit AdvanceTo(sampleCount) called from the mix path — and state in the header which clock each console passes.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
