# ADR-0041: MEP `audio` section — v1 host scope is NES OGG only

- Status: accepted
- Date: 2026-08-24
- Phase: F3.0 (MEP v1 host)

## Context
MEP-v1 §5.2 lets `audio.path` point at OGG replacement (via hires.txt `<bgm>`/
`<sfx>` tags) for NES and, through the still-draft hires-gbsms extension, for
GB/SMS; or MSU-1 for SNES. In the host today: NES OGG works (`OggMixer`
driven by `HdPackLoader`); the GB/SMS `HdTilePack` loader logs "not supported
yet" for those tags; MSU-1 exists only in the SNES core, which is outside the
PRD phases.

## Decision
For the F3 host implementation the `audio` section is honoured **only for
NES**, and it is realised as a hires.txt: `audio.path` must contain a
`hires.txt` whose `<bgm>`/`<sfx>` tags reference OGG files in that folder.
The manager loads it through the same `HdPackLoader::LoadHdNesPack(string)`
call used for textures, into the same `HdPackData`; when a pack has both
`textures` and `audio`, the `textures` hires.txt is loaded first and the
`audio` hires.txt second, only its BGM/SFX tables being merged. A pack whose
`audio` section targets GB/GBC/SMS/GG/SNES is accepted (valid pack) but the
section is skipped with a log line: "audio section not supported for <system>
in this version".

The MEP spec is **not** changed — this is a documented host limitation
(README roadmap + `docs/specs/README.md` note), lifted when the hires-gbsms
extension freezes (issue #1) and when/if SNES enters a later phase.

## Consequences
- The F3 success criterion (NES: textures + OGG BGM + synth preset, each
  toggleable) is fully reachable.
- An audio-only NES pack (OGG music without texture replacement) is possible
  today: a hires.txt with only `<bgm>` tags.
- Pack authors targeting GB/SMS audio get an explicit log instead of silence.

## Alternatives
- Block F3 on the hires-gbsms audio freeze: couples two roadmaps. Rejected.
- Invent a MEP-specific audio manifest: violates the envelope principle
  (MEP-v1 §1). Rejected.
