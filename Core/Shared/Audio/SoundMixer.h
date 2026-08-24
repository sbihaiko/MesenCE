#pragma once
#include "pch.h"
#include "Core/Shared/Interfaces/IAudioDevice.h"
#include "Utilities/safe_ptr.h"
#include "Utilities/Audio/HermiteResampler.h"

class Emulator;
class Equalizer;
class SoundResampler;
class WaveRecorder;
class VgmExporter;
class MidiExporter;
class IAudioProvider;
class CrossFeedFilter;
class ReverbFilter;

class SoundMixer
{
private:
	IAudioDevice* _audioDevice;
	vector<IAudioProvider*> _audioProviders;
	Emulator* _emu;
	unique_ptr<Equalizer> _equalizer;
	unique_ptr<SoundResampler> _resampler;
	safe_ptr<WaveRecorder> _waveRecorder;

	//Music captures, owned per-Emulator like _waveRecorder (ADR-0012). The
	//chip write-sites and synth wrappers read them through GetVgmExporter()/
	//GetMidiExporter() - a plain pointer load, safe because Start/Stop only
	//run while the emulation thread is paused (Emulator::AcquireLock() in the
	//interop layer, or emulator teardown).
	safe_ptr<VgmExporter> _vgmExporter;
	safe_ptr<MidiExporter> _midiExporter;

	int16_t* _sampleBuffer = nullptr;

	HermiteResampler _pitchAdjust;
	int16_t* _pitchAdjustBuffer = nullptr;

	int16_t _leftSample = 0;
	int16_t _rightSample = 0;

	unique_ptr<CrossFeedFilter> _crossFeedFilter;
	unique_ptr<ReverbFilter> _reverbFilter;

	void ProcessEqualizer(int16_t* samples, uint32_t sampleCount, uint32_t targetRate);

public:
	SoundMixer(Emulator* emu);
	~SoundMixer();

	void PlayAudioBuffer(int16_t* samples, uint32_t sampleCount, uint32_t sourceRate);
	void StopAudio(bool clearBuffer = false);

	void RegisterAudioDevice(IAudioDevice* audioDevice);

	void RegisterAudioProvider(IAudioProvider* provider);
	void UnregisterAudioProvider(IAudioProvider* provider);

	AudioStatistics GetStatistics();
	double GetRateAdjustment();

	void StartRecording(string filepath);
	void StopRecording();
	bool IsRecording();

	//Music captures (VGM / MIDI). Start/Stop must run while the emulation
	//thread is paused - see the comment on the members above. Start displays
	//a MessageManager error and records nothing when the file can't be
	//opened (ADR-0033); StartMidiRecording also emits a one-line notice when
	//Enhanced Audio is off, since the MIDI capture will then be empty
	//(ADR-0014). Both captures stop on ROM load/unload and power-off, and
	//survive a soft reset.
	void StartVgmRecording(string filepath);
	void StopVgmRecording();
	bool IsVgmRecording();
	void StartMidiRecording(string filepath);
	void StopMidiRecording();
	bool IsMidiRecording();

	//Hot-path accessors for the tap sites: nullptr when not recording, so
	//`if(VgmExporter* vgm = mixer->GetVgmExporter())` is the whole guard -
	//a couple of dependent loads and a branch, no lock or refcount traffic
	//(ADR-0011).
	VgmExporter* GetVgmExporter() { return _vgmExporter.get(); }
	MidiExporter* GetMidiExporter() { return _midiExporter.get(); }

	void GetLastSamples(int16_t& left, int16_t& right);
};
