# ADR-0142: Crossfade for replaced BGM transitions (F5.4g Block C item 10)

- Status: accepted 2026-08-29 (contract reflected in the code since `c36043f5`; accepted by user decision with the click-free listening verification recorded as manual-pending — see Consequences)
- Date: 2026-08-29
- Related: ADR-0133 (per-channel mute mask — the other Block C audio item), ADR-0134 (loop point), ADR-0052 (level-2 classifier; it already crossfades on role changes — the same philosophy applies here)

## Context

A fingerprint match starts a replacement OGG via `HdAudioDevice::PlayReplacementBgm`
→ `OggMixer::Play`, which **atomically replaces** `_bgm` (`OggMixer.cpp:103`):
the previous track's `OggReader` is dropped mid-sample. When the game switches
music (overworld → battle, stage → boss), the replacer matches the new track
and the old OGG is cut instantly — an audible click, and the new track starts
from its first sample with no ramp. `OggMixer::StopBgm()` (`:44`) also drops
`_bgm` instantly. Neither path ramps volume, so both a hard cut and a stop
produce a click in the replacement path.

The codebase already establishes crossfade as the answer to abrupt audio
switches: the level-2 classifier crossfades its synth voices on role changes
(ADR-0052), and ADR-0133's Alternatives record that "a crossfade could hide
role flips" as a deferred idea. Item 10 applies the same idea at the OGG
layer: when one replacement track gives way to another, overlap the two for a
short window instead of cutting.

## Decision

A short, fixed crossfade in `OggMixer`, driven entirely by the real-audio mix
path (never by run-ahead frames):

1. **Releasing track.** `OggMixer` keeps one fading-out reader alongside the
   current `_bgm`: `_bgmFadeOut` plus a sample counter. `Play(isSfx=false)`
   moves the existing `_bgm` into `_bgmFadeOut` (resetting any prior releasing
   track — rapid switches cut the oldest, never stack readers) and starts the
   new `_bgm` with a fade-in counter. `StopBgm()` does the same move instead
   of an instant `reset()`.
2. **Fixed window.** `kBgmFadeSamples = 1764` (~40 ms at 44.1 kHz) — short
   enough to feel immediate, long enough to kill the click; the same order as
   the classifier's own crossfades. A constant, not a setting: this is a
   transition cosmetic, not a mix parameter.
3. **Ramps.** In `MixAudio`, the current `_bgm` mixes at `_bgmVolume * fadeIn`
   where `fadeIn` ramps 0→1 over the window; `_bgmFadeOut` mixes at
   `_bgmVolume * fadeOut` where `fadeOut` ramps 1→0. Both write into the same
   `out` buffer, so the window genuinely overlaps. Counters decrement only on
   non-run-ahead samples (an `OggReader::ApplySamples` already no-ops on
   run-ahead, `OggReader.cpp:68`; the fade counters must not advance on frames
   that produce no audio, or the fade would finish before the sound does).
4. **Lifetime.** `_bgmFadeOut` is dropped when its counter hits 0 or its
   reader reports playback over; `Reset()` clears it and both counters.
5. **SFX untouched.** Only the BGM path fades; `_sfx` keeps its current
   behavior (one-shot effects, no ramp).

## Consequences

- A music switch and a stop in the replacement path no longer click: the old
  track's last ~40 ms overlap the new one's first ~40 ms.
- One extra `OggReader` alive for ≤ 40 ms per switch; no allocation in the
  per-sample loop (the fade is a per-flush volume, reusing the existing
  `ApplySamples` volume parameter).
- Fade-in on first start removes the start click too (a fresh `_bgm` begins
  at 0 and ramps up).
- Validation: headless `roles_probe`-style run with a two-track pack whose
  tracks the game switches between (e.g. Zelda overworld → dungeon) — no
  click at the boundary; run-ahead ≥ 1 frame still produces correct audio
  (fades not consumed by discarded frames). Listening/regression on real
  games is recorded as manual-pending per the standing "podemos seguir sem
  testar?" precedent.
- Accepted 2026-08-29 by user decision: the crossfade shipped (`c36043f5`);
  the click-free switch/stop verification on a real pack is recorded as
  manual-pending (listening validation — loop-intro, SFX audibility, no click
  on switch), not a blocker for the acceptance.
- **Defect found and fixed 2026-09-03 (bug
  https://github.com/sbihaiko/MesenCE/issues/151).** The shipped fade was
  block-stepped, not a ramp: `MixAudio` computed one `fadeIn`/`fadeOut` factor
  per call and handed `ApplySamples` a single `uint8_t` volume for the whole
  block. `SoundMixer::PlayAudioBuffer` calls `MixAudio` once per emulated frame
  (~735 samples at 44.1 kHz / 60 Hz), so a `kBgmFadeSamples = 1764` window was
  2-3 volume steps of roughly 40 % each — a quieter click, not a crossfade, and
  not the "no click at the boundary" contract this ADR states. Decision 3's
  "ramps 0→1 over the window" is unchanged and `kBgmFadeSamples` stays 1764;
  what changed is *where* the ramp is applied: the volume is now interpolated
  **per sample inside the block**. `MixAudio` passes the block's start **and**
  end factor down (`OggFadeRamp::MixSamples`, 16.16 fixed point so the ramp is
  finer than its 8-bit endpoints); when the window ends mid-block the block is
  split so the ramp finishes exactly at `kBgmFadeSamples` — the fade-in's
  remainder mixes at the steady volume, the fade-out's remainder is not mixed
  at all. A block with no fade in progress still takes the constant-volume fast
  path, so a non-fading mix costs what it did before.
- Consequence of the fix on testability: `OggMixer`/`OggReader` no longer take
  a concrete `Emulator`. The run-ahead probe is an injected
  `std::function<bool()>` and the mixer drives its voices through the new
  `IOggSource` interface, both bound at the single real construction site
  (`HdAudioDevice`). That makes the crossfade linkable into the makefile's
  `core-unit-tests` target, which deliberately links neither `Emulator` nor
  stb_vorbis. Public behaviour is unchanged.
- The "click-free listening verification" is therefore no longer the only
  evidence: `scripts/core_unit_tests.cpp` Bloco I drives the mixer with two
  constant-amplitude `IOggSource` stubs in real 735-sample blocks (play A →
  switch to B → `StopBgm`) and asserts no sample-to-sample jump beyond the two
  linear ramps' slope, that each envelope tracks its linear curve within the
  8-bit volume quantisation, silence after the stop window, and that a
  run-ahead block advances neither the fade counters nor the sources. Against
  the pre-fix block-stepped code those assertions fail by ~1900 units.
- Implementation state (verified 2026-09-01; line numbers predate the
  2026-09-03 ramp fix): `Core/NES/HdPacks/OggMixer.h:19`
  (`kBgmFadeSamples = 1764`), `OggMixer.cpp:47-56` (`StopBgm` moves `_bgm` into
  `_bgmFadeOut`), `:117-118` (`Play` does the same on a switch), `:142-164`
  (fade-in/fade-out ramps gated on `!IsRunAheadFrame()`), `Reset` clears both
  (`:21-23`). SFX path unchanged. The Context's `OggMixer.cpp:103`/`:44` line
  numbers are those of the pre-`c36043f5` file.

## Alternatives

- **Fade-through-silence** (ramp out, then start the new track) — simpler
  (no overlap, no second reader) but leaves a dip at the switch and still
  needs the old reader alive during its ramp-out; the overlap version is the
  same machinery with a better result.
- **Fade-in only, instant stop** — removes the start click but leaves the
  stop/switch click; half the fix.
- **Do nothing** (current hard cut) — the status quo; rejected: the switch
  click is the most audible defect of the replacement path after the loop
  point (ADR-0134).
