# ADR-0047: BGM/SFX trigger without ROM patch — APU register fingerprints

- Status: proposed
- Date: 2026-08-25
- Fase 5, F5.3. Sits beside the HDNes `$41xx` mechanism, does not replace it.

## Context
HDNes audio (`<bgm>/<sfx>` → `HdAudioDevice` → `OggMixer`) needs the *game*
to write to `$4100+`, which only happens with an IPS that patches the sound
engine — invasive, per-revision, and the reason Zelda Remastered rejected all
of the user's dumps. Our F1 exporter already observes every APU register write
per channel to build MIDI/VGM; the start of a track is a highly distinctive
sequence of those writes.

## Decision
- Authoring (`scripts/`): segment the recorded MIDI/VGM into tracks; for each,
  store a fingerprint = first N frames of per-channel (period, volume, duty)
  writes normalised to relative pitch and frame deltas → `audio/fingerprints.json`
  with `{ id, kind: bgm|sfx, frames, tolerance, file }`.
- Host: a `FingerprintMatcher` fed by the same tap the F1 exporter uses;
  on a match confirmed over K frames it raises the same events the
  `HdAudioDevice` would (play/loop/stop track, mute APU) into `OggMixer`.
  Track end/loop detected by the game's own APU silence or by the next match.
- Toggle per pack in the `audio` section; IPS-based packs unaffected.
- NES only for now (ADR-0041 scope); design is chip-agnostic.

## Consequences
- Packs become revision-independent for audio and need no patch.
- False positives are the main risk: K-frame confirmation, per-track tolerance,
  and the `sfx` window kept short. Metrics in the F5.3 headless validation.
- Real-time cost: O(active fingerprints × N) per frame — trivial.
