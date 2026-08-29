#pragma once
#include "pch.h"
#include "Shared/Interfaces/IAudioProvider.h"

class OggReader;
class Emulator;

class OggMixer : public IAudioProvider
{
private:
	shared_ptr<OggReader> _bgm;
	//F5.4g Block C item 10 (ADR-0142): a releasing track overlapping the
	//current one for a short crossfade window when the BGM switches or stops.
	shared_ptr<OggReader> _bgmFadeOut;
	//Sample counters counting down from kBgmFadeSamples: the current _bgm
	//ramps 0->1 over its window, the releasing track 1->0 over its own.
	uint32_t _bgmFadeInSamplesLeft = 0;
	uint32_t _bgmFadeOutSamplesLeft = 0;
	static constexpr uint32_t kBgmFadeSamples = 1764; //~40ms at 44.1kHz

	vector<shared_ptr<OggReader>> _sfx;

	Emulator* _emu = nullptr;
	uint32_t _sampleRate = 0;
	uint8_t _bgmVolume = 0;
	uint8_t _sfxVolume = 0;
	uint8_t _options = 0;
	bool _paused = false;

public:
	OggMixer(Emulator* emu);
	virtual ~OggMixer() = default;

	void SetSampleRate(int sampleRate);

	void Reset(uint32_t sampleRate);
	bool Play(string filename, bool isSfx, uint32_t startOffset, uint32_t loopPosition);
	void SetPlaybackOptions(uint8_t options);
	void SetPausedFlag(bool paused);
	void StopBgm();
	void StopSfx();
	void SetBgmVolume(uint8_t volume);
	void SetSfxVolume(uint8_t volume);
	bool IsBgmPlaying();
	bool IsSfxPlaying();
	int32_t GetBgmOffset();

	void MixAudio(int16_t* out, uint32_t sampleCount, uint32_t sampleRate) override;
};
