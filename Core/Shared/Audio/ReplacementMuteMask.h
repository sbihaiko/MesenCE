#pragma once
#include <cstdint>

//F5.4g Block C item 9 (ADR-0133): the per-channel replacement mute mask, in
//one host-free place so the two halves of the contract cannot drift - the
//policy (NesAudioReplacer, which channels stay muted while a replacement OGG
//plays) and the application (NesSoundMixer::GetChannelOutput, which bit
//silences which channel).
//
//One bit per melodic/DMC channel index: 0 Square1, 1 Square2, 2 Triangle,
//3 Noise, 4 DMC. Expansion channels (FDS, MMC5, VRC6, VRC7, Namco163,
//Sunsoft5B) have no bit and always pass, matching pre-item-9 behaviour.
//
//This header deliberately depends on nothing: the mixer must not pull in
//Core/Shared/Audio/ChannelRoleClassifier (ADR-0133 rejects coupling the mixer
//to the classifier), so Compute() is a template over the classifier type
//rather than an include.
namespace ReplacementMuteMask
{
	//The four tonal channels muted wholesale before item 9, and the fallback
	//for every degraded mode (classification off, classifier not warmed up).
	static constexpr uint8_t FullTonalMute = 0x0F;
	//Channels the classifier can flag as SFX (Square1, Square2, Triangle).
	static constexpr int MelodicChannelCount = 3;
	//No mask bit exists above this index; DMC keeps bit 4 but is never set by
	//Compute(), and everything above it is expansion audio.
	static constexpr int DmcChannelIndex = 4;

	inline bool IsMuted(uint8_t mask, int channelIndex)
	{
		return (mask & (1 << channelIndex)) != 0;
	}

	//Recomputes the mask from the ChannelRoleClassifier: a melodic channel with
	//a stable SFX flag has its bit cleared so it passes through dry while the
	//OGG replaces the music. A null classifier (Enhanced Audio off) - and,
	//through IsSfx() itself, SFX separation off or a classifier that has not
	//warmed up - leaves the full tonal mute, never "unmute all", which would
	//play the music twice.
	template<typename TClassifier>
	inline uint8_t Compute(const TClassifier* roles)
	{
		uint8_t mask = FullTonalMute;
		if(roles) {
			for(int i = 0; i < MelodicChannelCount; i++) {
				if(roles->IsSfx(i)) {
					mask &= ~(uint8_t)(1 << i);
				}
			}
		}
		return mask;
	}
}
