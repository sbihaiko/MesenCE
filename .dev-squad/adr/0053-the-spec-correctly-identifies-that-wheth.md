# ADR-0053: The spec correctly identifies that whether UI.Tests.csproj joins Mese...

- Status: proposed
- Date: 2026-08-26

## Context
Raised during spec: The spec correctly identifies that whether UI.Tests.csproj joins Mesen.sln affects Windows-only CI (dotnet-format-check.yml's `dotnet restore` + `dotnet format --verify-no-changes`, and any `-r win-x64 -p:PublishAot=true` restore), but cannot be executed/verified from this non-Windows actor environment. The spec resolves this by having the actor record a decision (include vs. exclude, with rationale) in UI/AGENTS.md rather than run the Windows verification.

## Decision
Default to keeping UI.Tests.csproj OUT of Mesen.sln for this PR (the new unit-tests.yml workflow calls the csproj directly, so sln membership isn't required for CI to pass) and record that as the documented decision, leaving future sln inclusion as a decision to revisit once verified on Windows.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
