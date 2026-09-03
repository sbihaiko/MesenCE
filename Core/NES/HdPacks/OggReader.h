#pragma once
#include "pch.h"
#include "Utilities/VirtualFile.h"
#include "Utilities/Audio/HermiteResampler.h"
#include "NES/HdPacks/IOggSource.h"
#include <functional>

struct stb_vorbis;

class OggReader : public IOggSource
{
private:
	stb_vorbis* _vorbis = nullptr;
	int16_t* _outputBuffer = nullptr;
	int16_t* _oggBuffer = nullptr;

	HermiteResampler _resampler;
	//ADR-0142: injected run-ahead probe instead of a concrete Emulator, so the
	//OGG path can be built without linking the emulator (see IOggSource).
	std::function<bool()> _isRunAheadFrame;

	bool _loop = false;
	bool _done = false;

	uint32_t _loopPosition = 0;

	int _sampleRate = 0;
	int _oggSampleRate = 0;

	vector<uint8_t> _fileData;

public:
	OggReader(std::function<bool()> isRunAheadFrame);
	~OggReader();

	bool Init(string filename, bool loop, uint32_t sampleRate, uint32_t startOffset = 0, uint32_t loopPosition = 0);
	bool IsPlaybackOver() override;
	void SetSampleRate(int sampleRate) override;
	void SetLoopFlag(bool loop) override;
	void ApplySamples(int16_t* buffer, size_t sampleCount, uint8_t volumeStart, uint8_t volumeEnd) override;
	uint32_t GetOffset() override;
};
