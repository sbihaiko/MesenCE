#pragma once
#include "pch.h"
#include "Utilities/VirtualFile.h"
#include "Utilities/Audio/HermiteResampler.h"
#include "NES/HdPacks/IOggSource.h"
#include "NES/HdPacks/OggLoopStream.h"
#include <functional>
#include <memory>

class OggReader : public IOggSource
{
private:
	//ADR-0134: the read/loop rule lives in OggLoopStream, driven by a decoder
	//interface, so it can be unit-tested without stb_vorbis or VirtualFile.
	std::unique_ptr<IOggDecoder> _decoder;
	OggLoopStream _stream;

	int16_t* _outputBuffer = nullptr;
	int16_t* _oggBuffer = nullptr;

	HermiteResampler _resampler;
	//ADR-0142: injected run-ahead probe instead of a concrete Emulator, so the
	//OGG path can be built without linking the emulator (see IOggSource).
	std::function<bool()> _isRunAheadFrame;

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
