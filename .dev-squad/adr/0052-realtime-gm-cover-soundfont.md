# ADR-0052: Sound level 2 — automatic GM cover from live APU state, SoundFont timbres

- Status: proposed
- Date: 2026-08-25
- Fase 5, F5.4g. Builds on F1 (`EnhancedSynth`/`EnhancedSynthEngine`), ADR-0042 (ESP per pack), ADR-0047/0051 (track identification).

## Context
Two roads were explored for better game audio without a human in the loop:
identify each track (fingerprint, F5.3; driver discovery, ADR-0051) and swap it
for a rendered/handmade OGG, or re-interpret the chip state live. The first
only pays off when a human provides the OGG — a SoundFont render of the
extracted MIDI sounds no better than live re-synthesis — and it only covers the
tracks somebody reached (~50 % of ROMs for the driver route). The second is
what the F1 Enhanced Audio already does for every game from the first frame,
but with fixed channel roles (pulse1 = lead, pulse2 = harmony, triangle =
bass), DSP-only timbres and no notion of SFX: Mario's jump plays with the lead
patch and the bass turns into a melody when the composer swaps channels.

## Decision
Make the live re-synthesis the **default audio layer** (level 2) and grow it
into an automatic "GM cover", all at run time, no `auto/` files, no human step:

1. **Channel role per window** (~1 s): mean register, note density and length,
   interval relation to the triangle → lead / harmony / bass, with hysteresis
   and a crossfade on role changes.
2. **SFX vs music**: short bursts, fast glides, retriggers, a channel stolen and
   handed back → routed dry (or raw APU) instead of the music patch. This same
   classifier later lets SFX through while an OGG replaces the music (3b).
3. **Arpeggio → chord**: a periodic 2–4 note alternation at 20–60 Hz becomes a
   sustained chord.
4. **Expression**: decay, vibrato and portamento read from the APU pick the
   patch family (pluck × sustained × strings) and modulate the voice.
5. **Timbres**: TinySoundFont (header-only, MIT) renders General MIDI programs
   from a SoundFont; role + expression → GM program table.
6. Human override stays optional in the pack's `synth/preset.cfg` (ESP): role
   and program per channel for a given game.

SoundFont sourcing: ship a small GM SoundFont (a few MB, permissive licence)
so the level works offline out of the box; if `EnhancedAudio.SoundFontPath`
points to a bigger `.sf2` (e.g. MuseScore General, already used by
`mep_render_audio.py`) use it; if neither loads, fall back to the current DSP
voices. A SoundFont is data, not a heavy tool — this stays within the PRD rule
of never embedding heavy pipelines.

Track identification (3a) and human OGGs (3b) sit **on top**: 3a never changes
the sound by itself, 3b overrides level 2 only for the tracks that exist.

## Consequences
- `+` Every ROM sounds "remastered" on first load with intact SFX; ROM hacks too.
- `+` The SFX classifier fixes the F5.3 defect where whole channels are muted
  during OGG playback.
- `−` Heuristics can misjudge a role for a second — mitigated by hysteresis and
  crossfades; a wrong SFX call plays a short note with the wrong patch.
- `−` One more audio dependency (TinySoundFont) and a bundled SoundFont in the
  repo/installer (size and licence to confirm before accepting).
- Validation: headless harness comparing the MIDI captured before/after the
  new mapping on Zelda, Mega Man and SMB3, plus listening in the GUI.
