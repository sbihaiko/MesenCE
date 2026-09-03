#pragma once
#include "pch.h"

//ADR-0142: the audio source OggMixer drives. OggReader is the only production
//implementation; the interface exists so the mixer's crossfade logic can be
//built and unit-tested without stb_vorbis, VirtualFile or the emulator (the
//`core-unit-tests` target deliberately links neither).
class IOggSource
{
public:
	virtual ~IOggSource() = default;

	virtual bool IsPlaybackOver() = 0;
	virtual void SetSampleRate(int sampleRate) = 0;
	virtual void SetLoopFlag(bool loop) = 0;

	//Mixes the next sampleCount stereo frames into buffer, ramping the volume
	//linearly from volumeStart to volumeEnd across the block (ADR-0142: the
	//fade is a per-sample ramp, not one volume step per MixAudio call).
	virtual void ApplySamples(int16_t* buffer, size_t sampleCount, uint8_t volumeStart, uint8_t volumeEnd) = 0;

	virtual uint32_t GetOffset() = 0;
};
