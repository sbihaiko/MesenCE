# ADR-0042: ESP preset override layer — defaults < MEP synth section < user file

- Status: accepted
- Date: 2026-08-24
- Phase: F3.0 (MEP v1 host); implements ADR-0008 (synth is F3's first real consumer).

## Context
`EnhancedSynthPresetLoader::Load(out, defaults, suffix)` copies the built-in
presets and then applies `<home>/EnhancedAudioPresets.cfg`. MEP-v1 §5.3 says a
pack's `synth` file applies *above* the built-ins and *below* the user's
file. The loader is called by each engine (NES/GB/SMS) on reset/ROM load and
must not do anything new on the audio path.

## Decision
`EnhancedSynthPresetLoader::Load` gains an optional layer: after copying the
defaults it applies, in order, (1) the MEP `synth` file supplied by
`MepPackManager` (`GetSynthPresetPath()`, empty when no pack/section or when
the section is disabled), then (2) the user's `EnhancedAudioPresets.cfg`.
Both files use the same ESP v1 parser (`ApplyFile(path, out, suffix)` —
the existing loop factored into a helper); a pack file that fails to open is
logged and skipped. Engines obtain the pack path through
`Emulator::GetEnhancementPackManager()`, so the loader signature keeps its
current three parameters plus one `const string& packPresetPath`.

## Consequences
- "User always wins" holds field-by-field: a user file that sets only
  `CompThreshold` keeps every other pack value.
- No behaviour change when no MEP pack is installed (empty path → old path).
- Section suffixes (`""`, `.Gb`, `.Sms`) work identically in pack files, so
  a single pack preset can tune all three engines.

## Alternatives
- Make the pack file *replace* the user's file: violates §5.3.
- Merge at struct level in the manager: duplicates the ESP parser. Rejected.
