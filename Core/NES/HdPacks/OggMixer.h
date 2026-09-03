#pragma once
#include "pch.h"
#include "Shared/Interfaces/IAudioProvider.h"
#include "NES/HdPacks/IOggSource.h"
#include <functional>

class OggMixer : public IAudioProvider
{
public:
	//ADR-0142: the mixer no longer knows about OggReader or Emulator. Both the
	//run-ahead probe and the source factory are injected by the real
	//construction site (HdAudioDevice), which keeps the crossfade logic
	//buildable without stb_vorbis/VirtualFile/Emulator - see IOggSource.
	//The factory returns nullptr when the file cannot be opened.
	typedef std::function<shared_ptr<IOggSource>(string filename, bool loop, uint32_t sampleRate, uint32_t startOffset, uint32_t loopPosition)> SourceFactory;

private:
	shared_ptr<IOggSource> _bgm;
	//F5.4g Block C item 10 (ADR-0142): a releasing track overlapping the
	//current one for a short crossfade window when the BGM switches or stops.
	shared_ptr<IOggSource> _bgmFadeOut;
	//Sample counters counting down from kBgmFadeSamples: the current _bgm
	//ramps 0->1 over its window, the releasing track 1->0 over its own.
	uint32_t _bgmFadeInSamplesLeft = 0;
	uint32_t _bgmFadeOutSamplesLeft = 0;
	static constexpr uint32_t kBgmFadeSamples = 1764; //~40ms at 44.1kHz

	vector<shared_ptr<IOggSource>> _sfx;

	std::function<bool()> _isRunAheadFrame;
	SourceFactory _createSource;
	uint32_t _sampleRate = 0;
	uint8_t _bgmVolume = 0;
	uint8_t _sfxVolume = 0;
	uint8_t _options = 0;
	bool _paused = false;

	void MixFaded(IOggSource* source, int16_t* out, uint32_t sampleCount, uint32_t samplesLeft, bool fadeIn);

public:
	OggMixer(std::function<bool()> isRunAheadFrame, SourceFactory createSource);
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
