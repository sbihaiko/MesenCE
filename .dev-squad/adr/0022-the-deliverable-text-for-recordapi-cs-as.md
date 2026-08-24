# ADR-0022: The deliverable text for RecordApi.cs asks for all six new DllImport ...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during spec: The deliverable text for RecordApi.cs asks for all six new DllImport bindings (MidiRecord/MidiStop/MidiIsRecording/VgmRecord/VgmStop/VgmIsRecording), but AC-13's verification command only greps for `MidiRecord`, leaving the VgmRecord half of that same file unverified by any AC.

## Decision
Add a companion grep (e.g. `grep -n "VgmRecord" UI/Interop/RecordApi.cs`) alongside AC-13, or extend AC-12/AC-13 to check both symbols, so the interop bindings for both exporters are independently verifiable rather than relying on AC-16's full build to catch an omission.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
