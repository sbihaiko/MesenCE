# ESP v1 — Enhanced Synth Preset

**Status:** v1 (stable) ·
**License for this spec:** CC0-1.0 (public domain) ·
**Versioning:** semver — new field = minor; semantic change or removal = major ·
**Golden file:** [`golden/esp/EnhancedAudioPresets.cfg`](golden/esp/EnhancedAudioPresets.cfg) ·
**Validation:** `scripts/validate-specs.py`

The keywords MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY follow
[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

## 1. Scope

ESP describes the file format for Enhanced Audio *presets*: the voice
parameters a parallel synthesizer uses to reinterpret, in real time, the
state of the classic sound chips (NES APU/2A03, Game Boy APU, the SMS/GG/
SG-1000/ColecoVision SN76489, and the YM2413 melodic bus). The reference
implementation is MesenCE (`Core/Shared/Audio/EnhancedSynthPreset.*`), but
any emulator MAY implement the format.

The file does NOT contain data derived from any ROM — only synthesis
parameters — and is therefore always distributable.

## 2. Data model

An implementation exposes **5 named presets**, each existing per **engine**
(chip/family). The ESP file contains *partial overrides* applied on top of
the implementation's built-in defaults.

- Preset names (MUST, case-sensitive): `Synthwave`, `ChipDeluxe`,
  `OrchestralLite`, `Dry`, `Studio`.
- Engine suffixes (MUST): empty = NES APU, `.Gb` = Game Boy APU,
  `.Sms` = SMS family (SN76489 + YM2413).
- Implementations that support other chips MAY define new suffixes; an
  unknown suffix MUST be ignored by the parser (future compatibility).

## 3. Grammar

Line-oriented text file, ASCII/UTF-8 encoding.

```
file      := line*
line      := blank | comment | section | field
comment   := ('#' | ';') any-text
section   := '[' PresetName EngineSuffix ']'
field     := Name '=' Value
```

Normative rules:

1. Whitespace at the ends of each line MUST be trimmed before parsing.
2. Blank lines and comments MUST be ignored.
3. A `field` only takes effect within a recognized `section`; fields before
   the first section MUST be ignored.
4. Section and field names are **case-sensitive** (MUST).
5. An unknown field, malformed line, or non-numeric value (for numeric
   fields) MUST be silently ignored — the file is never rejected in its
   entirety.
6. An omitted field MUST retain the preset/engine's built-in default
   (partial override). v1 fallback rule: **field → built-in default of the
   (preset, engine) pair**. Per-game fallback (hash) is reserved for a
   future version (see §6).
7. Booleans accept `true`/`false` (MUST).

## 4. Fields

All numeric fields are decimal floating-point (`0.25`, `5200`).

### 4.1 Pulse voices (lead / harmony)

| Field | Type | Unit / semantics |
|---|---|---|
| `LeadDetune` | double | detune ratio between the lead's 2 oscillators (0.003 = ±0.3%) |
| `HarmDetune` | double | same, for the harmony voice |
| `FollowDuty` | bool | true: pulse width follows the game's duty register (no effect on chips without duty) |
| `FixedWidth` | double | pulse width 0..1 used when `FollowDuty=false` |
| `LeadAlwaysSaw` | bool | true: lead becomes a stack of detuned saws; duty ignored |
| `LeadOctaveUpMix` | double | 0..1 mix of a +1 octave copy in the lead |
| `LeadLpHz` | double | lead low-pass cutoff, Hz |
| `HarmLpHz` | double | harmony low-pass cutoff, Hz |
| `LeadDrive` | double | lead saturation gain (1 = neutral) |

### 4.2 Bass (triangle channel / tone 2)

| Field | Type | Semantics |
|---|---|---|
| `BassSine` | double | level of the sine component |
| `BassSaw` | double | level of the saw component |
| `BassSub` | double | level of the sub-oscillator (−1 octave) |
| `BassLpHz` | double | bass low-pass cutoff, Hz |
| `BassDrive` | double | bass saturation (1 = neutral) |

### 4.3 Drums (noise channel)

| Field | Type | Semantics |
|---|---|---|
| `DrumBodyLoHz` | double | lower band of the body, Hz |
| `DrumBodyHiHz` | double | upper band of the body, Hz |
| `DrumTopHz` | double | high-pass of the "top" (hi-hat), Hz |
| `DrumBodyGain` | double | level of the body |
| `ThumpGain` | double | level of the synthetic kick triggered by a low attack |
| `ThumpDecayS` | double | kick decay, seconds |
| `ThumpFreqHz` | double | kick frequency, Hz |

### 4.4 Envelope, FX, and mix

| Field | Type | Semantics |
|---|---|---|
| `AttackMs` / `ReleaseMs` | double | volume smoothing time constants, ms |
| `EchoDelayS` | double | lead echo delay, seconds |
| `EchoGainL` / `EchoGainR` | double | echo level per side (stereo image) |
| `ReverbWet` | double | level of the 3-tap feedforward reverb |
| `LeadGain` / `HarmGain` / `BassGain` / `DrumGain` | double | voice levels in the mix |

### 4.5 Master bus compressor

| Field | Type | Semantics |
|---|---|---|
| `CompThreshold` | double | level where compression begins; **0 disables the compressor** |
| `CompRatio` | double | compression ratio; values < 1 MUST be treated as 1 |
| `CompAttackMs` / `CompReleaseMs` | double | detector time constants, ms |
| `CompMakeup` | double | output makeup gain |

## 5. Reload semantics

Implementations SHOULD re-read the file on console reset / ROM switch and
MUST NOT perform file I/O on the audio mixing path.

## 6. Reserved for future versions (non-normative in v1)

- Per-game sections, proposed as `[<NomePreset><SufixoEngine>@<SHA1>]`
  (fallback game → engine → default). v1 parsers already ignore them
  naturally per rule §3.5.
- Additional engine suffixes (e.g., `.Pce`, `.Snes`).

## 7. Golden file

[`golden/esp/EnhancedAudioPresets.cfg`](golden/esp/EnhancedAudioPresets.cfg)
is the canonical example: it contains all engine sections, all v1 fields
with values within their usual ranges, comments, and one deliberate unknown
field (which conformant parsers ignore). `scripts/validate-specs.py`
validates it against this spec's grammar and field list.
