# ADR-0047: BGM/SFX trigger without ROM patch — APU register fingerprints

- Status: accepted (2026-08-25, F5.3 — `Core/Shared/EnhancementPacks/AudioFingerprint.*`, `Core/NES/HdPacks/NesAudioFingerprint.*`; fingerprint = first ≤32 onsets `[voice, relative pitch, frame]`, tolerance ±3 frames, confirmation after 8 onsets, 90 silent frames stop the OGG and restore the APU)
- Date: 2026-08-25
- Phase 5, F5.3. Sits beside the HDNes `$41xx` mechanism, does not replace it.

## Context
HDNes audio (`<bgm>/<sfx>` → `HdAudioDevice` → `OggMixer`) needs the *game*
to write to `$4100+`, which only happens with an IPS that patches the sound
engine — invasive, per-revision, and the reason Zelda Remastered rejected all
of the user's dumps. Our F1 exporter already observes every APU register write
per channel to build MIDI/VGM; the start of a track is a highly distinctive
sequence of those writes.

## Decision
- Authoring (`scripts/`): segment the recorded MIDI/VGM into tracks; for each,
  store a fingerprint = the first ≤32 note onsets, each as `[voice, pitchRel,
  frame]` (pitch relative to the track's first onset, frame relative to the
  track start) → `audio/fingerprints.json` with the schema documented in
  MEP-v1 §5.2:
  `{ "version": 1, "tracks": [ { "id", "kind": "bgm"|"sfx", "frames", "midi": "midi/<id>.mid", "events": [[voice, pitchRel, frame], …] } ] }`.
  The OGG to play is `bgm/<id>.ogg` (or `sfx/<id>.ogg`) by naming
  convention (ADR-0049) — there is no per-track `file` field, and the frame
  tolerance is not stored per track.
- Host: a `FingerprintMatcher` fed by the same tap the F1 exporter uses;
  onsets are matched with a host-constant tolerance of ±3 frames, and a
  match is confirmed after 8 onsets agree, at which point it raises the same
  events the `HdAudioDevice` would (play/loop/stop track, mute APU) into
  `OggMixer`. 90 consecutive silent APU frames stop the OGG and restore the
  APU; the next confirmed match also ends the current track.
- Toggle per pack in the `audio` section; IPS-based packs unaffected.
- NES only for now (ADR-0041 scope); design is chip-agnostic.

## Consequences
- Packs become revision-independent for audio and need no patch.
- False positives are the main risk: the 8-onset confirmation, the ±3-frame
  host tolerance, and the `sfx` window kept short. Metrics in the F5.3 headless validation.
- Real-time cost: O(active fingerprints × N) per frame — trivial.
