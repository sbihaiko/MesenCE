#include "pch.h"
#include "NES/HdPacks/OggReader.h"
#include "NES/HdPacks/OggFadeRamp.h"
#include "Utilities/Audio/stb_vorbis.h"

OggReader::OggReader(std::function<bool()> isRunAheadFrame)
{
	_isRunAheadFrame = isRunAheadFrame;
	_done = false;
	_oggBuffer = new int16_t[10000];
	_outputBuffer = new int16_t[2000];
}

OggReader::~OggReader()
{
	delete[] _oggBuffer;
	delete[] _outputBuffer;

	if(_vorbis) {
		stb_vorbis_close(_vorbis);
	}
}

bool OggReader::Init(string filename, bool loop, uint32_t sampleRate, uint32_t startOffset, uint32_t loopPosition)
{
	int error;
	VirtualFile file = filename;
	_fileData = vector<uint8_t>(100000);
	if(file.ReadFile(_fileData)) {
		_vorbis = stb_vorbis_open_memory(_fileData.data(), (int)_fileData.size(), &error, nullptr);
		if(_vorbis) {
			_loop = loop;
			if(loopPosition > 0) {
				unsigned int sampleCount = stb_vorbis_stream_length_in_samples(_vorbis);
				_loopPosition = loopPosition < sampleCount ? loopPosition : 0;
			} else {
				_loopPosition = 0;
			}
			_oggSampleRate = stb_vorbis_get_info(_vorbis).sample_rate;
			if(startOffset > 0) {
				stb_vorbis_seek(_vorbis, startOffset);
			}
			return true;
		}
	}
	return false;
}

bool OggReader::IsPlaybackOver()
{
	return _done;
}

void OggReader::SetSampleRate(int sampleRate)
{
	if(sampleRate != _sampleRate) {
		_sampleRate = sampleRate;
	}
}

void OggReader::SetLoopFlag(bool loop)
{
	_loop = loop;
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
		uint32_t samplesLoaded = (uint32_t)stb_vorbis_get_samples_short_interleaved(_vorbis, 2, _oggBuffer, samplesToLoad * 2);
		if(samplesLoaded < samplesToLoad) {
			if(_loop) {
				stb_vorbis_seek(_vorbis, _loopPosition);
				samplesLoaded += stb_vorbis_get_samples_short_interleaved(_vorbis, 2, _oggBuffer + samplesLoaded * 2, (samplesToLoad - samplesLoaded) * 2);
			} else {
				_done = true;
			}
		}
		_resampler.SetSampleRates(_oggSampleRate, _sampleRate);
		samplesRead = _resampler.Resample<false>(_oggBuffer, samplesLoaded, _outputBuffer, sampleCount);
	}

	//ADR-0142: the volume is interpolated per sample across the block, so a
	//fade is a ramp instead of one step per MixAudio call.
	OggFadeRamp::MixSamples(buffer, _outputBuffer, samplesRead, (uint32_t)sampleCount, volumeStart, volumeEnd);
}

uint32_t OggReader::GetOffset()
{
	return stb_vorbis_get_sample_offset(_vorbis);
}