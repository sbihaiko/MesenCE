# ADR-0133: Per-channel replacement mute mask in NesSoundMixer (Block C item 9)

- Status: proposed (write-before-implement: Block C of the F5 closeout never executed; nothing in the tree implements this yet)
- Date: 2026-08-27
- Consolidates: ADR-0094, ADR-0097
- Related: ADR-0052 item 2 (SFX vs music classifier — parent decision), ADR-0047 (fingerprint trigger), ADR-0051

## Context

When a fingerprint match starts an OGG replacement, `NesAudioReplacer::OnFrame`
(`Core/NES/HdPacks/NesAudioFingerprint.cpp:155`) calls
`NesSoundMixer::SetReplacementMute(true)`; on stop or when pack audio is
disabled it calls `SetReplacementMute(false)` (`:130`, `:144`). The mixer
(`Core/NES/NesSoundMixer.h:18`, `_replacementMute` at `:48`) applies it in
`GetChannelOutput` (`NesSoundMixer.cpp:174`): while set, every channel whose
index is `<= AudioChannel::Noise` (Square1, Square2, Triangle, Noise) returns
0; DMC and expansion audio keep playing. This is the F5.3 defect ADR-0052
names: whole channels are muted during OGG playback, so SFX that the game
plays on those channels (jumps, hits, menu cues) disappear while the music is
replaced.

ADR-0052 decided the *classifier* (`Core/Shared/Audio/ChannelRoleClassifier`,
Block A, shipped) and states that "this same classifier later lets SFX through
while an OGG replaces the music (3b)". It did not decide the *mixer API
contract* that makes that possible. The F5 closeout spec (dev-squad run
`d662e62e2648`, Block C item 9) planned to replace `SetReplacementMute(bool)`
with a per-channel `SetReplacementMuteMask` driven by the classifier, and
claimed no new ADR was needed. ADR-0094 and ADR-0097 dispute that: changing a
core audio API in the mixer hot path deserves a recorded contract (mask
semantics, fate of the boolean setter, ownership of the split, behaviour when
classification is unavailable). That run never executed — `git log -S
SetReplacementMuteMask` hits only the ADR commit — so the decision is still
open and must be written before Block C is (re)scheduled.

## Decision

Proposed contract for Block C item 9:

1. **API.** Add `void SetReplacementMuteMask(uint8_t mask)` to `NesSoundMixer`,
   one bit per `AudioChannel` index 0..4 (Square1, Square2, Triangle, Noise,
   DMC); a set bit means "silence this channel while a replacement plays".
   `GetChannelOutput` tests `mask & (1 << (int)channel)` instead of the
   `<= Noise` range check. Expansion channels (FDS, MMC5, VRC6, VRC7, Namco163,
   Sunsoft5B) are never masked, matching today's behaviour.
2. **Boolean setter kept as a thin shim, then removed.** `SetReplacementMute(true)`
   becomes `SetReplacementMuteMask(0x0F)` (the four channels muted today) and
   `SetReplacementMute(false)` becomes `SetReplacementMuteMask(0)`, so
   `NesAudioFingerprint.cpp:130,144,155` compile unchanged in the first commit.
   Callers are migrated to the mask in the same block and the bool is deleted
   before Block C closes; no deprecated API survives into a release.
3. **Ownership.** The mixer owns nothing but the mask; it makes no music/SFX
   judgement. `NesAudioReplacer` owns the policy: it computes the mask each
   frame from the `ChannelRoleClassifier` output (channels flagged SFX get their
   bit cleared so they pass through dry; channels classified as music stay
   muted while the OGG plays) and pushes it to the mixer only when it changes.
4. **Degraded modes.** When classification is unavailable (`EnhancedAudioSfxSeparation`
   off, classifier not warmed up, or role mid-hysteresis) the mask falls back to
   the full `0x0F`, i.e. exactly today's behaviour — never to "unmute all",
   which would double the music. A channel is unmasked only on a stable SFX
   flag; hysteresis is the classifier's (ADR-0052 item 1), not the mixer's.
5. **Reset.** Any stop path (`StopReplacementBgm`, pack audio disabled, ROM
   reset, `NesSoundMixer::Reset`) clears the mask to 0.

## Consequences

- SFX on pulse/triangle/noise are heard during OGG replacement, closing the F5.3
  defect that ADR-0052 promised to fix, without touching `HdAudioDevice` or the
  OGG path.
- One extra 8-bit test per channel sample in `GetChannelOutput`; no new
  allocation or lock in the hot path.
- GB/SMS mixers are out of scope: only the NES replacer drives OGG replacement
  today (`docs/specs/MEP-v1.md` §5.2 lists OGG for GB/SMS only via the draft
  extension).
- Validation before acceptance: `scripts/roles_probe`-style headless run on
  SMB1 (jump SFX audible while the overworld OGG plays), Zelda (music muted, sword
  audible), plus a check that turning `EnhancedAudioSfxSeparation` off restores
  the exact pre-Block-C output.
- This ADR moves to `accepted` when the mask lands and the bool setter is gone.

## Alternatives

- **Keep the boolean, do the split elsewhere** (e.g. re-synthesise SFX from the
  Enhanced Audio engine while the APU stays fully muted) — rejected: the raw
  APU SFX are the correct sound; ADR-0052 item 2 routes SFX "dry (or raw APU)".
- **Mixer consults the classifier directly** — rejected: couples
  `Core/NES/NesSoundMixer` to `Core/Shared/Audio`, and puts policy in the hot
  path; the replacer already owns the match/stop lifecycle.
- **Per-channel float attenuation instead of a bit mask** — deferred; a
  crossfade could hide role flips, but the classifier already crossfades on
  role changes and a bit mask keeps the contract trivially testable.
- **Unmute all on classification loss** — rejected (music would play twice).
