#pragma once
#include "pch.h"
#include <algorithm>

//ADR-0142: the shared mixing kernel of the BGM crossfade. The fade volume used
//to be a single uint8_t per MixAudio call, i.e. one step per ~735-sample block
//over a 1764-sample window (2-3 steps of ~40%) - a quieter click, not a ramp.
//The volume is now interpolated per sample between the block's start and end
//factors, in 16.16 fixed point so the ramp is finer than its 8-bit endpoints.
namespace OggFadeRamp
{
	static constexpr int kVolumeShift = 16;

	//Mixes `frames` interleaved stereo frames of `src` into `dst`, ramping the
	//volume from volumeStart to volumeEnd over `rampFrames` frames. `frames`
	//may be shorter than `rampFrames` when the source runs out mid-block; the
	//slope stays the one the block asked for so the ramp is continuous across
	//blocks. volumeStart == volumeEnd takes the constant-volume fast path, so
	//a non-fading mix costs exactly what it did before.
	inline void MixSamples(int16_t* dst, const int16_t* src, uint32_t frames, uint32_t rampFrames, uint8_t volumeStart, uint8_t volumeEnd)
	{
		if(volumeStart == volumeEnd || rampFrames == 0) {
			int32_t volume = volumeStart;
			for(uint32_t i = 0, count = frames * 2; i < count; i++) {
				dst[i] = std::clamp<int32_t>((int32_t)(src[i] * volume / 255) + dst[i], INT16_MIN, INT16_MAX);
			}
			return;
		}

		int64_t volume = (int64_t)volumeStart << kVolumeShift;
		int64_t step = ((((int64_t)volumeEnd - (int64_t)volumeStart) << kVolumeShift)) / (int64_t)rampFrames;
		for(uint32_t f = 0; f < frames; f++) {
			for(uint32_t c = 0; c < 2; c++) {
				uint32_t i = f * 2 + c;
				int64_t scaled = ((int64_t)src[i] * volume) / (255 << kVolumeShift);
				dst[i] = std::clamp<int64_t>(scaled + dst[i], INT16_MIN, INT16_MAX);
			}
			volume += step;
		}
	}
}
