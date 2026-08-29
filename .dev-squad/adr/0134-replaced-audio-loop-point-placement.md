# ADR-0134: Loop point placement for replaced audio tracks (fingerprint field vs OGG tags)

- Status: proposed (open — no option chosen yet; decide before F5 closeout item 8 is scheduled)
- Date: 2026-08-29 (restored from b0b334b0^; originally dated 2026-08-27)
- Consolidates: ADR-0095, ADR-0098
- Related: ADR-0052 (orthogonal — level 2 audio; the loop point is F5.3/3b territory), ADR-0047 (fingerprint trigger)

## Context

A replacement OGG chosen by fingerprint match today always loops from sample 0:
`NesAudioReplacer` builds a `BgmTrackInfo` with `info.LoopPosition = 0`
(`Core/NES/HdPacks/NesAudioFingerprint.cpp:112`; struct at
`Core/NES/HdPacks/HdData.h:463-467`). The player already supports a loop point:
`OggReader::Init(filename, loop, sampleRate, startOffset, loopPosition)`
(`Core/NES/HdPacks/OggReader.h:33`, `.cpp:24-37`) clamps `loopPosition` to
`< sampleCount` and loops back to it. Game music almost always has an intro
that must not repeat, so the missing piece is *where the loop point comes from*
for MEP audio.

The F5 closeout spec (run `d662e62e2648`, item 8) planned an optional `loop`
field on each track in `audio/fingerprints.json` plus a minor MEP spec bump.
Neither shipped: `docs/specs/MEP-v1.md` §5.2 documents the schema as
`{ "version": 1, "tracks": [ { "id", "kind", "frames", "midi", "events" } ] }`
with no `loop`, and `Core/Shared/EnhancementPacks/AudioFingerprint.h:54` matches
it. ADR-0095 flagged that the field's unit/range and the compatibility rule for
packs omitting it were spread over three tasks with no owner; ADR-0098 asked the
prior question — why should the loop point live in the fingerprint at all,
rather than in the OGG file the `OggReader` already parses?

## Decision

Open question, stated crisply: **for a replacement track, is the loop point a
property of the identification record (`fingerprints.json`) or of the audio
asset (the OGG)?**

Option A — `loop` field in `fingerprints.json`:
- `tracks[i].loop` (optional, integer, unit fixed once in MEP-v1: PCM sample
  offset at the OGG's own rate, or milliseconds — not APU frames, since
  `frames` on the same object counts emulated frames of the *original* track,
  and the OGG length is unrelated to it).
- Bumps `fingerprints.json` `"version"` to 2 or adds the field under version 1
  as optional; MEP-v1 §5.2 gets a minor revision.
- Written by the human who renders/edits the OGG (the bootstrap cannot know the
  loop point of a file it did not produce), read by `NesAudioReplacer` into
  `BgmTrackInfo::LoopPosition`.

Option B — loop point in the OGG's own metadata:
- Vorbis comment tags `LOOPSTART`/`LOOPLENGTH` (the RPG Maker / game-audio
  convention) or an equivalent tag, read by `OggReader` when the file is opened
  and applied as `loopPosition`.
- No schema or spec change; the asset carries its own loop; the same OGG loops
  identically in any player that honours the tag.
- Requires reading Vorbis comments in `OggReader` (not done today).

Rule regardless of option — **backward compatibility for packs that omit it**:
a track without a loop point keeps today's behaviour, `LoopPosition = 0`
(loop the whole file). Hosts MUST ignore an unknown field/tag rather than
reject the pack; `scripts/mep_lint.py` MUST accept both the presence and the
absence of the field/tag under MEP-v1.

## Consequences

- Until decided, replaced tracks loop from the start; intros repeat. No code
  change is blocked except item 8 itself.
- Option A keeps the loop point next to the track id (easy to lint, easy to
  edit in one JSON) but duplicates an asset property into the manifest and
  drifts if the OGG is re-rendered; it also needs a spec bump and a unit
  definition.
- Option B keeps the asset self-describing and spec-neutral, but the value is
  invisible to `mep_lint.py` unless the linter also parses Vorbis comments, and
  authoring requires a tagging tool.
- Either way `mep_render_audio.py` (which renders MIDI to OGG) is the natural
  place to emit the loop point for machine-rendered tracks, since the MIDI's
  loop marker, if any, is known there.

## Alternatives

- **Do nothing** (loop from 0 forever) — rejected: intros repeating is the most
  audible defect of the current replacement path.
- **Loop point in `audio/hires.txt` `<bgm>` lines** (the native HD pack tag's
  optional 4th token is already parsed into `BgmTrackInfo::LoopPosition`,
  `Core/NES/HdPacks/HdPackLoader.cpp:847-865`) — viable for hand-written
  HD packs but not for fingerprint-matched tracks, whose ids are assigned at
  load (`TrackIdBase + i`), so it would tie the human to generated ids.
- **Both A and B, with A overriding B** — possible fallback if authoring tools
  cannot tag OGGs; costs two code paths and two places to disagree.
