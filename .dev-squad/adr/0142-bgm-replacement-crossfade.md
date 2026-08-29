# ADR-0142: Crossfade for replaced BGM transitions (F5.4g Block C item 10)

- Status: proposed (write-before-implement: Block C item 10 has no recorded contract; nothing in the tree implements a fade today)
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
- This ADR moves to `accepted` when the crossfade ships and the switch/stop
  boundary is verified click-free on a real pack.

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
