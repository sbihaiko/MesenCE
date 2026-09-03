#include "pch.h"
#include <algorithm>
#include "NES/HdPacks/OggMixer.h"

enum class OggPlaybackOptions
{
	None = 0x00,
	Loop = 0x01
};

OggMixer::OggMixer(std::function<bool()> isRunAheadFrame, SourceFactory createSource)
{
	_isRunAheadFrame = isRunAheadFrame;
	_createSource = createSource;
}

void OggMixer::Reset(uint32_t sampleRate)
{
	_bgm.reset();
	_bgmFadeOut.reset();
	_bgmFadeInSamplesLeft = 0;
	_bgmFadeOutSamplesLeft = 0;
	_sfx.clear();
	_sfxVolume = 128;
	_bgmVolume = 128;
	_options = 0;
	_sampleRate = sampleRate;
	_paused = false;
}

void OggMixer::SetPlaybackOptions(uint8_t options)
{
	_options = options;

	bool loop = (options & (int)OggPlaybackOptions::Loop) != 0;
	if(_bgm) {
		_bgm->SetLoopFlag(loop);
	}
}

void OggMixer::SetPausedFlag(bool paused)
{
	_paused = paused;
}

void OggMixer::StopBgm()
{
	//F5.4g Block C item 10 (ADR-0142): fade the current track out instead of
	//cutting it; a lone fade-in (no releasing track) still removes the stop
	//click, and a switch later takes over the releasing slot.
	if(_bgm) {
		_bgmFadeOut = _bgm;
		_bgmFadeOutSamplesLeft = kBgmFadeSamples;
		_bgm.reset();
	}
}

void OggMixer::StopSfx()
{
	_sfx.clear();
}

void OggMixer::SetBgmVolume(uint8_t volume)
{
	_bgmVolume = volume;
}

void OggMixer::SetSfxVolume(uint8_t volume)
{
	_sfxVolume = volume;
}

bool OggMixer::IsBgmPlaying()
{
	return !_paused && _bgm;
}

bool OggMixer::IsSfxPlaying()
{
	return _sfx.size() > 0;
}

void OggMixer::SetSampleRate(int sampleRate)
{
	_sampleRate = sampleRate;
	if(_bgm) {
		_bgm->SetSampleRate(sampleRate);
	}
	for(shared_ptr<IOggSource>& sfx : _sfx) {
		sfx->SetSampleRate(sampleRate);
	}
}

bool OggMixer::Play(string filename, bool isSfx, uint32_t startOffset, uint32_t loopPosition)
{
	bool loop = !isSfx && (_options & (int)OggPlaybackOptions::Loop) != 0;
	shared_ptr<IOggSource> reader = _createSource(filename, loop, _sampleRate, startOffset, loopPosition);
	if(reader) {
		if(_isRunAheadFrame && _isRunAheadFrame()) {
			//If this was done on runahead frames, SFX/BGM will attempt to start playing multiple times (once per runahead frame)
			//This causes all sound effects to be duplicated.
			//Skipping the processing on runahead here is an imperfect workaround - it allows 1 runahead frame to usually work properly
			//but attempting to use over 1 frame of runahead will instead cause SFX to not play properly at times.
			//Ideally, the exact state of the BGM/SFX (what is playing exactly, and at which part of their playback they are) should
			//be part of the save state data and restored like any other state (but this isn't trivial to implement at the moment)
			return true;
		}

		if(isSfx) {
			_sfx.push_back(reader);
		} else {
			//F5.4g Block C item 10 (ADR-0142): a music switch crossfades - the
			//old track becomes the releasing reader and the new one fades in.
			//A rapid second switch replaces the releasing slot (never stacks).
			if(_bgm) {
				_bgmFadeOut = _bgm;
				_bgmFadeOutSamplesLeft = kBgmFadeSamples;
			}
			_bgm = reader;
			_bgmFadeInSamplesLeft = kBgmFadeSamples;
		}
		return true;
	}
	return false;
}

int OggMixer::GetBgmOffset()
{
	if(_bgm) {
		return _bgm->GetOffset();
	} else {
		return -1;
	}
}

//ADR-0142: mixes one block of a fading source, interpolating the volume per
//sample between the block's start and end factors. The fade used to be a
//single uint8_t per MixAudio call, i.e. one step per ~735-sample block over a
//1764-sample window (2-3 steps of ~40%) - an audible click, not a crossfade
//(https://github.com/sbihaiko/MesenCE/issues/151). When the window ends inside
//the block the block is split, so the ramp finishes exactly at
//kBgmFadeSamples: the fade-in's remainder mixes at the steady volume, and the
//fade-out's remainder is silence and is not mixed at all.
void OggMixer::MixFaded(IOggSource* source, int16_t* out, uint32_t sampleCount, uint32_t samplesLeft, bool fadeIn)
{
	auto factor = [fadeIn](uint32_t left) {
		double ratio = (double)left / kBgmFadeSamples;
		return fadeIn ? 1.0 - ratio : ratio;
	};

	if(samplesLeft == 0) {
		//No fade in progress: one constant volume, the pre-ADR-0142 fast path.
		uint8_t volume = (uint8_t)(_bgmVolume * factor(0) + 0.5);
		source->ApplySamples(out, sampleCount, volume, volume);
		return;
	}

	uint32_t rampCount = samplesLeft < sampleCount ? samplesLeft : sampleCount;
	//Rounded, not truncated: the endpoints are the only place the ramp is
	//quantised to 8 bits, so half an LSB of error is worth the +0.5.
	uint8_t volumeStart = (uint8_t)(_bgmVolume * factor(samplesLeft) + 0.5);
	uint8_t volumeEnd = (uint8_t)(_bgmVolume * factor(samplesLeft - rampCount) + 0.5);
	source->ApplySamples(out, rampCount, volumeStart, volumeEnd);
	if(rampCount < sampleCount && fadeIn) {
		source->ApplySamples(out + rampCount * 2, sampleCount - rampCount, volumeEnd, volumeEnd);
	}
}

void OggMixer::MixAudio(int16_t* out, uint32_t sampleCount, uint32_t sampleRate)
{
	//F5.4g Block C item 10 (ADR-0142): the fade counters advance only on real
	//audio (not run-ahead frames - the source's ApplySamples no-ops on those,
	//so advancing here would burn the fade on audio that never plays).
	bool realAudio = !_isRunAheadFrame || !_isRunAheadFrame();

	if(_bgm && !_paused) {
		_bgm->SetSampleRate(sampleRate);
		MixFaded(_bgm.get(), out, sampleCount, _bgmFadeInSamplesLeft, true);
		if(realAudio && _bgmFadeInSamplesLeft > 0) {
			_bgmFadeInSamplesLeft = _bgmFadeInSamplesLeft > sampleCount ? _bgmFadeInSamplesLeft - sampleCount : 0;
		}
		if(_bgm->IsPlaybackOver()) {
			_bgm.reset();
		}
	}
	if(_bgmFadeOut && !_paused) {
		_bgmFadeOut->SetSampleRate(sampleRate);
		MixFaded(_bgmFadeOut.get(), out, sampleCount, _bgmFadeOutSamplesLeft, false);
		if(realAudio) {
			_bgmFadeOutSamplesLeft = _bgmFadeOutSamplesLeft > sampleCount ? _bgmFadeOutSamplesLeft - sampleCount : 0;
		}
		if(_bgmFadeOut->IsPlaybackOver() || _bgmFadeOutSamplesLeft == 0) {
			_bgmFadeOut.reset();
		}
	}
	for(shared_ptr<IOggSource>& sfx : _sfx) {
		sfx->SetSampleRate(sampleRate);
		sfx->ApplySamples(out, sampleCount, _sfxVolume, _sfxVolume);
	}
	_sfx.erase(std::remove_if(_sfx.begin(), _sfx.end(), [](const shared_ptr<IOggSource>& o) { return o->IsPlaybackOver(); }), _sfx.end());
}
