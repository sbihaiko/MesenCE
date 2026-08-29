#pragma once
#include "pch.h"
#include "Utilities/ISerializable.h"
#include "Utilities/Audio/blip_buf.h"
#include "Utilities/Audio/StereoDelayFilter.h"
#include "Utilities/Audio/StereoPanningFilter.h"
#include "Utilities/Audio/StereoCombFilter.h"
#include "NesTypes.h"

class NesConsole;
class SoundMixer;
class EmuSettings;
enum class ConsoleRegion;

class NesSoundMixer : public ISerializable
{
public:
	//F5.4g Block C item 9 (ADR-0133): per-channel replacement mute mask - one
	//bit per AudioChannel index 0..4 (Square1, Square2, Triangle, Noise, DMC);
	//a set bit silences that channel while a replacement OGG plays. The mixer
	//owns nothing but the mask; the policy (which channels stay muted) is
	//NesAudioReplacer's, computed from the ChannelRoleClassifier.
	void SetReplacementMuteMask(uint8_t mask) { _replacementMuteMask = mask; }
	static constexpr uint32_t CycleLength = 10000;
	static constexpr uint32_t BitsPerSample = 16;

private:
	static constexpr uint32_t MaxSampleRate = 96000;
	static constexpr uint32_t MaxSamplesPerFrame = MaxSampleRate / 60 * 4 * 2; //x4 to allow CPU overclocking up to 10x, x2 for panning stereo
	static constexpr uint32_t MaxChannelCount = 11;

	NesConsole* _console = nullptr;
	SoundMixer* _mixer = nullptr;

	StereoPanningFilter _stereoPanning;
	StereoDelayFilter _stereoDelay;
	StereoCombFilter _stereoCombFilter;

	int16_t _previousOutputLeft = 0;
	int16_t _previousOutputRight = 0;

	vector<uint32_t> _timestamps;
	int16_t _channelOutput[MaxChannelCount][CycleLength] = {};
	int16_t _currentOutput[MaxChannelCount] = {};

	blip_t* _blipBufLeft = nullptr;
	blip_t* _blipBufRight = nullptr;
	int16_t* _outputBuffer = nullptr;
	size_t _sampleCount = 0;
	double _volumes[MaxChannelCount] = {};
	//F5.3/Block C item 9 (ADR-0133): the fingerprint replacer mutes the tonal
	//APU channels while an OGG plays (DMC/FDS/expansion audio untouched); the
	//mask lets SFX-flagged melodic channels pass through dry. Default 0 = no
	//replacement playing. Serialized as false on older saves - Reset clears it.
	uint8_t _replacementMuteMask = 0;
	double _enhancedDuck = 1.0;
	double _panning[MaxChannelCount] = {};

	uint32_t _sampleRate = 0;
	uint32_t _clockRate = 0;

	bool _hasPanning = false;

	__forceinline double GetChannelOutput(AudioChannel channel, bool forRightChannel);
	__forceinline int16_t GetOutputVolume(bool forRightChannel);
	void EndFrame(uint32_t time);

	void ProcessVsDualSystemAudio();

	void UpdateRates(bool forceUpdate);

public:
	NesSoundMixer(NesConsole* console);
	virtual ~NesSoundMixer();

	void SetRegion(ConsoleRegion region);
	void Reset();

	void PlayAudioBuffer(uint32_t cycle);
	void AddDelta(AudioChannel channel, uint32_t time, int16_t delta);

	void Serialize(Serializer& s) override;
};