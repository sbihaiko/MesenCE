# ADR-0008: F3 lands MepPack and EnhancementPackManager with no consumer anywhere...

- Status: proposed
- Date: 2026-08-24

## Context
Raised during decompose: F3 lands MepPack and EnhancementPackManager with no consumer anywhere in the tree: nothing in the ROM-load path constructs the manager, and neither HdNesPack (textures), OggMixer (audio) nor EnhancedSynthEngine/EnhancedSynthPreset (synth) is taught to read from a loaded pack. As planned, F3 compiles as dead code and the per-section TextureEnabled/AudioEnabled/SynthEnabled toggles have no effect on anything. The ACs (greps only) will not catch this.

## Decision
Decide explicitly whether F3 is scoped as a library-only phase (state so in the spec, and defer the integration point to a named follow-up) or whether it must include one real consumption point — most cheaply the synth section feeding EnhancedSynthPreset, which already has a config-file loader to mirror.

## Consequences
(to be assessed on acceptance)

## Alternatives
(to be enumerated on acceptance)
