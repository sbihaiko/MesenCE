#include "pch.h"
#include "NES/HdPacks/OggReader.h"
#include "NES/HdPacks/OggFadeRamp.h"
#include "Utilities/Audio/stb_vorbis.h"

namespace
{
	//ADR-0134: the production IOggDecoder - the only place that knows about
	//stb_vorbis. OggLoopStream drives it and owns the loop rule.
	class StbVorbisDecoder : public IOggDecoder
	{
	private:
		stb_vorbis* _vorbis = nullptr;

	public:
		StbVorbisDecoder(stb_vorbis* vorbis) : _vorbis(vorbis) {}

		~StbVorbisDecoder()
		{
			if(_vorbis) {
				stb_vorbis_close(_vorbis);
			}
		}

		int GetSampleRate() override { return stb_vorbis_get_info(_vorbis).sample_rate; }
		uint32_t GetStreamLength() override { return stb_vorbis_stream_length_in_samples(_vorbis); }
		void Seek(uint32_t sampleOffset) override { stb_vorbis_seek(_vorbis, sampleOffset); }
		uint32_t GetOffset() override { return stb_vorbis_get_sample_offset(_vorbis); }

		uint32_t ReadFrames(int16_t* buffer, uint32_t frames) override
		{
			return (uint32_t)stb_vorbis_get_samples_short_interleaved(_vorbis, 2, buffer, frames * 2);
		}
	};
}

OggReader::OggReader(std::function<bool()> isRunAheadFrame)
{
	_isRunAheadFrame = isRunAheadFrame;
	_oggBuffer = new int16_t[10000];
	_outputBuffer = new int16_t[2000];
}

OggReader::~OggReader()
{
	delete[] _oggBuffer;
	delete[] _outputBuffer;
}

bool OggReader::Init(string filename, bool loop, uint32_t sampleRate, uint32_t startOffset, uint32_t loopPosition)
{
	int error;
	VirtualFile file = filename;
	_fileData = vector<uint8_t>(100000);
	if(file.ReadFile(_fileData)) {
		stb_vorbis* vorbis = stb_vorbis_open_memory(_fileData.data(), (int)_fileData.size(), &error, nullptr);
		if(vorbis) {
			_decoder.reset(new StbVorbisDecoder(vorbis));
			_stream.Init(_decoder.get(), loop, loopPosition);
			_oggSampleRate = _decoder->GetSampleRate();
			if(startOffset > 0) {
				_decoder->Seek(startOffset);
			}
			return true;
		}
	}
	return false;
}

bool OggReader::IsPlaybackOver()
{
	return _stream.IsDone();
}

void OggReader::SetSampleRate(int sampleRate)
{
	if(sampleRate != _sampleRate) {
		_sampleRate = sampleRate;
	}
}

void OggReader::SetLoopFlag(bool loop)
{
	_stream.SetLoopFlag(loop);
}

void OggReader::ApplySamples(int16_t* buffer, size_t sampleCount, uint8_t volumeStart, uint8_t volumeEnd)
{
	if(_isRunAheadFrame && _isRunAheadFrame()) {
		return;
	}

	int32_t samplesNeeded = (int32_t)sampleCount - _resampler.GetPendingCount();
	uint32_t samplesRead = 0;
	if(samplesNeeded > 0) {
		uint32_t samplesToLoad = samplesNeeded * _oggSampleRate / _sampleRate + 2;
		uint32_t samplesLoaded = _stream.Read(_oggBuffer, samplesToLoad);
		_resampler.SetSampleRates(_oggSampleRate, _sampleRate);
		samplesRead = _resampler.Resample<false>(_oggBuffer, samplesLoaded, _outputBuffer, sampleCount);
	}

	//ADR-0142: the volume is interpolated per sample across the block, so a
	//fade is a ramp instead of one step per MixAudio call.
	OggFadeRamp::MixSamples(buffer, _outputBuffer, samplesRead, (uint32_t)sampleCount, volumeStart, volumeEnd);
}

uint32_t OggReader::GetOffset()
{
	return _decoder ? _decoder->GetOffset() : 0;
}
