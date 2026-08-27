# ADR-0008: F3 scope — EnhancementPackManager ships with one real consumer (synth → EnhancedSynthPreset)

- Status: accepted
- Date: 2026-08-24

## Context
Raised during decompose: F3 lands MepPack and EnhancementPackManager with no consumer anywhere in the tree: nothing in the ROM-load path constructs the manager, and neither HdNesPack (textures), OggMixer (audio) nor EnhancedSynthEngine/EnhancedSynthPreset (synth) is taught to read from a loaded pack. As planned, F3 compiles as dead code and the per-section TextureEnabled/AudioEnabled/SynthEnabled toggles have no effect on anything. The ACs (greps only) will not catch this.

## Decision
F3 includes one real consumption point: the pack's synth/ section feeds EnhancedSynthPreset, mirroring its existing config-file loader. This gives the phase an end-to-end proof at minimal cost, exercises the ADR-0005 precedence rule, and validates EnhancementPackManager's API against a real caller. Library-only scoping is rejected: it would leave an entire phase unverifiable end-to-end.

## Consequences
The spec stops implying user-visible behaviour that F3 does not deliver. The synth-section consumer gives F3 an end-to-end proof at minimal cost and exercises the precedence rule from ADR-0005. Implemented by ADR-0042.

## Alternatives
Declare EnhancementPackManager library-only for F3 and let F4 be the first consumer (rejected): it would leave the spec honest about delivering no user-visible behaviour, but an entire phase would be unverifiable end-to-end and F3's API risks being wrong for its first real caller.
